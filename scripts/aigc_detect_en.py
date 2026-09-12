#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AIGC 文本检测器（英文版，启发式多指标，零依赖）
=================================================
在 scripts/aigc_detect.py 中文版基础上适配英文文本：
 - 以英文句号/问号/感叹号/分号切句（词级长度）
 - 英文 AI 高频套话/模板词库
 - 字级(字母)bigram 多样性、4-gram 重复率
 - 平均句长(词)、句长CV、突发度、数字密度、问叹句比例、段首连接词

评分：0~100 的「AI生成概率」。
      <30 倾向人类写作 | 30~60 可疑/混合 | >60 疑似AI生成。
⚠️ 本地启发式检测，用于写作自检，非商业检测系统。

用法：python3 scripts/aigc_detect_en.py <文本文件.txt或.md>
"""

import re
import sys
import math
import json
from collections import Counter

AI_PHRASES_EN = [
    # 总结性套话
    "in conclusion", "in summary", "overall,", "taken together", "it is evident that",
    "it goes without saying", "needless to say", "as is well known", "it is well known that",
    "it should be noted", "it is worth noting", "it is important to note", "it is noteworthy",
    "of note,", "notably,", "it is worth mentioning", "what is more", "more importantly",
    "importantly,", "firstly,", "secondly,", "thirdly,", "lastly,", "in addition",
    "moreover,", "furthermore,", "nevertheless,", "nonetheless,", "therefore,",
    "thus,", "hence,", "consequently,", "as a result", "on the one hand", "on the other hand",
    "in recent years", "with the rapid development", "in the era of", "in today's world",
    "plays an important role", "play a significant role", "has great significance",
    "has significant implications", "broad application prospects", "huge potential",
    "a wide range of", "a variety of", "an increasing number of", "a growing body of",
    "evidence suggests that", "studies have shown", "research has demonstrated",
    "it has been widely recognized", "it is widely accepted", "it is universally acknowledged",
    "in summary,", "in essence,", "in fact,", "in practice,", "to a certain extent",
    "to some degree", "as a matter of fact", "essentially,",
]

PARA_STARTERS_EN = ["In conclusion", "In summary", "Overall", "Furthermore", "Moreover",
                    "However", "Nevertheless", "Nonetheless", "Additionally", "Therefore",
                    "Thus", "Hence", "Finally", "Notably", "Importantly", "First",
                    "Second", "Third", "In addition", "Taken together", "On the other hand"]

def split_sentences(text):
    """按段落切 + 英文句读切句（保护小数点/常见缩写）"""
    sentences = []
    for para in re.split(r"\n+", text):
        para = para.strip()
        if not para:
            continue
        if re.match(r"^#{1,6}\s", para):
            continue
        # 先保护小数与常见缩写中的句点，避免切出伪句
        protected = re.sub(r"(?<=\d)\.(?=\d)", "\u0001", para)
        protected = re.sub(r"\b(et al|e\.g|i\.e|vs|Fig|Table|No|Dr|Prof|Mr|Mrs|Ms|etc)\.",
                           lambda m: m.group(0)[:-1] + "\u0002", protected, flags=re.I)
        parts = re.split(r"(?<=[.!?;])", protected)
        for p in parts:
            p = p.replace("\u0001", ".").replace("\u0002", ".")
            p = p.strip()
            if len(p.split()) >= 4:
                sentences.append(p)
    return sentences

def words_of(s):
    return re.findall(r"[A-Za-z][A-Za-z'\-]*", s)

def phrase_density(text):
    """套话密度：每千词命中次数"""
    total = len(words_of(text))
    if total == 0:
        return 0.0
    low = text.lower()
    hits = sum(low.count(p) for p in AI_PHRASES_EN)
    return hits * 1000.0 / total

def sentence_stats(sentences):
    if not sentences:
        return 0, 0, 0, 0
    lens = [len(words_of(s)) for s in sentences]
    n = len(lens)
    mean = sum(lens) / n
    std = math.sqrt(sum((x - mean) ** 2 for x in lens) / n) if n > 1 else 0
    cv = std / mean if mean > 0 else 0
    if n > 1:
        diffs = [abs(lens[i] - lens[i - 1]) for i in range(1, n)]
        burst = (sum(diffs) / len(diffs)) / mean if mean > 0 else 0
    else:
        burst = 0
    return n, mean, cv, burst

def bigram_diversity(text):
    """单词级 2-gram 多样性：唯一词对 / 总词对（英文用词对而非字母对）"""
    words = [w.lower() for w in words_of(text)]
    if len(words) < 40:
        return 0.5
    grams = [words[i] + "_" + words[i + 1] for i in range(len(words) - 1)]
    return len(set(grams)) / len(grams)

STOP_TOKENS = set("""a an the and or but if then than that this these those with without of in on at
to from by for as is are was were be been being has have had do does did not no
it its they them their we our you your i s t d m ve ll re can could should would
may might must will shall about between among into over under after before while
during through above below again further then once here there where why how all
any both each few more most other some such only own same so too very just also
figure fig table tables no e g et al doi""".split())

def _is_STOP(w):
    return w in STOP_TOKENS or len(w) <= 2 or ("-" in w and len(w.replace("-", "")) <= 3)

def repeat_4gram(text):
    """内容词重复 4-gram 占比：排除编号/专名/停用词干扰后的连续4词片段复用率"""
    words = [w.lower() for w in words_of(text)]
    if len(words) < 100:
        return 0.0
    out = []
    for i in range(len(words) - 3):
        w4 = words[i:i + 4]
        # 片段内含数字、单字母代号、纯停用词组合视为专名/惯用引用，不计入
        if any(ch.isdigit() for ch in " ".join(w4)):
            continue
        if sum(1 for w in w4 if _is_STOP(w)) >= 3:
            continue
        if any(len(w) <= 1 for w in w4):
            continue
        out.append("__".join(w4))
    if not out:
        return 0.0
    cnt = Counter(out)
    dup = sum(v for v in cnt.values() if v >= 2)
    return dup / len(out) if out else 0

def question_exclam_ratio(sentences):
    if not sentences:
        return 0.0
    q = sum(1 for s in sentences if re.search(r"[?!]", s))
    return q / len(sentences)

def number_density(text):
    total = len(words_of(text))
    if total == 0:
        return 0.0
    nums = len(re.findall(r"\d", text))
    return nums * 1000.0 / total

def para_starter_ratio(text):
    paras = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
    paras = [p for p in paras if not re.match(r"^#{1,6}\s", p)]
    if not paras:
        return 0.0
    hit = sum(1 for p in paras if any(p.startswith(w) for w in PARA_STARTERS_EN))
    return hit / len(paras)

def _norm(value, lo, hi):
    if hi == lo:
        return 0.5
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))

def score(text):
    sentences = split_sentences(text)
    n_sent, avg_len, cv, burst = sentence_stats(sentences)

    metrics = {
        "句子数": n_sent,
        "平均句长(词)": round(avg_len, 1),
        "句长CV": round(cv, 3),
        "突发度": round(burst, 3),
    }

    d_phrase = _norm(phrase_density(text), 0, 8)
    d_cv     = _norm(1 - cv, 0, 0.55) if cv > 0 else 0.9
    d_burst  = _norm(1 - burst, 0, 0.6) if burst > 0 else 0.9
    d_len    = _norm(avg_len, 12, 30)
    d_bigram = _norm(1 - bigram_diversity(text), 0, 0.25)
    d_4gram  = _norm(repeat_4gram(text), 0.001, 0.010)
    d_ques   = _norm(0.012 - question_exclam_ratio(sentences), 0, 0.012)
    d_num    = _norm(18 - number_density(text), 0, 18)
    d_para   = _norm(para_starter_ratio(text), 0, 0.5)

    weights = {
        "AI套话密度": 0.24,
        "句长均匀度CV": 0.16,
        "突发度": 0.10,
        "平均句长": 0.08,
        "用词多样性": 0.14,
        "重复短语率": 0.10,
        "问句/叹句比例": 0.06,
        "数字密度": 0.07,
        "段首连接词": 0.05,
    }
    vals = {
        "AI套话密度": d_phrase,
        "句长均匀度CV": d_cv,
        "突发度": d_burst,
        "平均句长": d_len,
        "用词多样性": d_bigram,
        "重复短语率": d_4gram,
        "问句/叹句比例": d_ques,
        "数字密度": d_num,
        "段首连接词": d_para,
    }
    total = sum(weights[k] * vals[k] for k in weights)
    score100 = round(total * 100, 1)

    details = {k: {"权重": weights[k], "得分": round(vals[k] * 100, 1)} for k in weights}
    details["原始指标"] = metrics

    hit_sents = []
    low_text = text.lower()
    for s in sentences:
        hits = [p for p in AI_PHRASES_EN if p in s.lower()]
        if hits:
            hit_sents.append({"句子": s[:90], "命中": hits[:4], "命中数": len(hits)})
    hit_sents.sort(key=lambda x: -x["命中数"])

    return score100, details, hit_sents

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        text = f.read()

    total, details, hit_sents = score(text)

    print("=" * 64)
    print(f"文件：{sys.argv[1]}")
    print(f"英文单词数：{len(words_of(text))}　句子数：{details['原始指标']['句子数']}")
    print("=" * 64)
    print(f"\n★ AIGC 生成概率评分：{total} / 100")
    if total < 30:
        print("  判定倾向：人类写作风格")
    elif total < 60:
        print("  判定倾向：可疑 / 人机混合（建议人工复核）")
    else:
        print("  判定倾向：疑似 AI 生成（AI痕迹明显）")
    print("\n" + "-" * 64)
    print("各维度明细（得分越高 = AI痕迹越重）：")
    for k in ["AI套话密度", "句长均匀度CV", "突发度", "平均句长",
              "用词多样性", "重复短语率", "问句/叹句比例", "数字密度", "段首连接词"]:
        d = details[k]
        flag = "▲" if d["得分"] >= 60 else ("△" if d["得分"] >= 40 else "○")
        print(f"  {flag} {k:<8} {d['得分']:5.1f}  (权重{d['权重']:.2f})")
    print("-" * 64)
    print(f"原始指标：{json.dumps(details['原始指标'], ensure_ascii=False)}")
    print("-" * 64)
    if hit_sents:
        print(f"\n命中套话/模板的句子 Top {min(12, len(hit_sents))}（改写优先）:")
        for i, h in enumerate(hit_sents[:12], 1):
            print(f"  [{i}] ({h['命中数']}处) {h['句子']}  ← {h['命中'][:3]}")
    print("\n⚠️ 本工具为本地启发式检测（演示/自检用途），非商业检测系统，仅供参考。")

if __name__ == "__main__":
    main()
