#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AIGC 文本检测器（启发式多指标，纯 Python 实现，零依赖）
==========================================================
用于「论文生成 → AIGC检测 → 迭代改写 → 复检」闭环测试。

检测维度（9项）：
 1. AI高频套话/连接词密度        —— AI 文本显著高于人类写作
 2. 句子长度变异系数 CV           —— AI 文本句长均匀（低CV）
 3. 文本突发度 burstiness         —— AI 文本相邻句长差异小（低突发度）
 4. 平均句长                     —— AI 文本偏好中长句
 5. 双字词(字级bigram)多样性      —— AI 文本用词重复度高、多样性低
 6. 重复4-gram占比               —— AI 文本高频复读固定短语
 7. 疑问/感叹句比例               —— AI 学术文本几乎为零
 8. 数字密度                     —— 人类论文含具体数据，AI 泛泛而谈
 9. 段首连接词比例               —— AI 文本段首习惯用"此外/然而/总之"

评分：各项归一化后加权求和 → 0~100 的「AI生成概率」。
      <30 倾向人类写作 | 30~60 可疑/混合 | >60 疑似AI生成。

⚠️ 免责声明：本工具为本地启发式检测，用于功能演示与写作自检，
   不等同于知网/维普/万方等商业 AIGC 检测系统，也不构成学术判定依据。

用法：python3 aigc_detect.py <文本文件.txt或.md>
"""

import re
import sys
import math
import json
from collections import Counter

# ==================== 中文 AI 高频套话/模板词库 ====================
AI_PHRASES = [
    # 总结性套话
    "综上所述", "总而言之", "总的来说", "总体而言", "由此可见", "不言而喻",
    "显而易见", "众所周知", "毋庸置疑", "值得一提的是", "值得注意的是",
    "值得关注的是", "值得注意的是", "需要指出的是", "需要强调的是",
    "不难发现", "不难看出", "由此可见",
    # 万能开头模板
    "随着", "近年来", "在当今", "在新时代", "与此同时", "在此背景下",
    "在这一背景下", "随着人工智能", "随着科技的", "在数字化",
    # 递进/转折连接
    "不仅", "而且", "此外", "同时", "然而", "但是", "因此", "因而",
    "从而", "进而", "由此可见", "一方面", "另一方面", "首先", "其次",
    "最后", "总之", "除此以外", "除此之外", "更重要的是", "更为重要的是",
    # 空洞评价词
    "具有重要意义", "重要作用", "重大意义", "深远影响", "广阔前景",
    "巨大潜力", "蓬勃发展", "日益凸显", "不断加强", "不断完善",
    "赋能", "助力", "抓手", "闭环", "落地", "场景化", "数字化", "智能化",
    "亟待解决", "刻不容缓", "任重道远",
    # 万能排比
    "不仅是", "更是", "既是", "又是", "从某种意义", "在某种程度上",
    "一定程度上", "事实上", "实际上", "本质上是", "从根本上",
    # 学术虚词堆砌
    "相关研究", "已有研究", "大量研究", "多项研究", "研究表明", "研究显示",
    "研究指出", "实验证明", "实践证明", "结果表明", "综上所述",
    "有效提升", "显著提升", "显著提高", "有效降低", "大幅提升",
]

# 段首连接词（出现在段落开头）
PARA_STARTERS = ["此外", "然而", "同时", "因此", "总之", "综上", "另外",
                 "其次", "最后", "首先", "值得注意的是", "总而言之",
                 "值得一提的是", "由此可见", "近年来", "随着", "在此基础上",
                 "另一方面", "除此之外", "更重要的是", "总体而言"]

# ==================== 文本预处理 ====================

def split_sentences(text):
    """按中文句读切分句子，返回句子列表（含长度信息）"""
    # 先按段落切，再按句号/感叹/问号/分号切
    sentences = []
    for para in re.split(r"\n+", text):
        para = para.strip()
        if not para:
            continue
        # 过滤标题行（# 开头）
        if re.match(r"^#{1,6}\s", para):
            continue
        parts = re.split(r"(?<=[。！？；!?;])", para)
        for p in parts:
            p = p.strip()
            if len(p) >= 4:  # 忽略过短片段
                sentences.append(p)
    return sentences

def strip_punct(s):
    return re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", s)

def chars_cn(s):
    """仅中文字符"""
    return re.sub(r"[^\u4e00-\u9fa5]", "", s)

# ==================== 分项指标 ====================

def phrase_density(text):
    """套话密度：每千字命中次数"""
    total = len(chars_cn(text))
    if total == 0:
        return 0.0
    hits = sum(text.count(p) for p in AI_PHRASES)
    return hits * 1000.0 / total

def sentence_stats(sentences):
    """句长统计：均值、CV、burstiness、句数"""
    if not sentences:
        return 0, 0, 0, 0
    lens = [len(chars_cn(s)) for s in sentences]
    n = len(lens)
    mean = sum(lens) / n
    std = math.sqrt(sum((x - mean) ** 2 for x in lens) / n) if n > 1 else 0
    cv = std / mean if mean > 0 else 0
    # burstiness：相邻句长差的均值 / 均值
    if n > 1:
        diffs = [abs(lens[i] - lens[i - 1]) for i in range(1, n)]
        burst = (sum(diffs) / len(diffs)) / mean if mean > 0 else 0
    else:
        burst = 0
    return n, mean, cv, burst

def bigram_diversity(text):
    """字级双字词多样性：唯一bigram / 总bigram"""
    cn = chars_cn(text)
    if len(cn) < 40:
        return 0.5
    grams = [cn[i:i + 2] for i in range(len(cn) - 1)]
    return len(set(grams)) / len(grams)

def repeat_4gram(text):
    """重复4-gram占比：出现≥2次的4字连续片段占总4-gram比例"""
    cn = chars_cn(text)
    if len(cn) < 100:
        return 0.0
    grams = [cn[i:i + 4] for i in range(len(cn) - 3)]
    cnt = Counter(grams)
    dup = sum(v for v in cnt.values() if v >= 2)
    return dup / len(grams) if grams else 0

def question_exclam_ratio(sentences):
    """疑问/感叹句占比"""
    if not sentences:
        return 0.0
    q = sum(1 for s in sentences if re.search(r"[？?!！]", s))
    return q / len(sentences)

def number_density(text):
    """数字密度：每千字数字个数"""
    total = len(chars_cn(text))
    if total == 0:
        return 0.0
    nums = len(re.findall(r"[0-9]", text))
    return nums * 1000.0 / total

def para_starter_ratio(text, sentences):
    """段首连接词比例：以连接词开头的段落 / 总段落"""
    paras = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
    paras = [p for p in paras if not re.match(r"^#{1,6}\s", p)]
    if not paras:
        return 0.0
    hit = sum(1 for p in paras if any(p.startswith(w) for w in PARA_STARTERS))
    return hit / len(paras)

# ==================== 归一化与加权评分 ====================

def _norm(value, lo, hi):
    """线性归一化到 0~1，clip 边界"""
    if hi == lo:
        return 0.5
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))

def score(text):
    """返回 (总分0~100, 各维度明细dict)"""
    sentences = split_sentences(text)
    n_sent, avg_len, cv, burst = sentence_stats(sentences)

    metrics = {
        "句数": n_sent,
        "平均句长(字)": round(avg_len, 1),
        "句长CV": round(cv, 3),
        "突发度": round(burst, 3),
    }

    # 各维度归一化（值越大 → AI概率分越高）
    d_phrase   = _norm(phrase_density(text), 0, 8)          # 每千字0~8次
    d_cv       = _norm(1 - cv, 0, 0.55) if cv > 0 else 0.9  # CV越低越AI
    d_burst    = _norm(1 - burst, 0, 0.6) if burst > 0 else 0.9
    d_len      = _norm(avg_len, 16, 34)                     # 句越长越AI
    d_bigram   = _norm(1 - bigram_diversity(text), 0, 0.4)  # 多样性越低越AI
    d_4gram    = _norm(repeat_4gram(text), 0.002, 0.02)
    d_ques     = _norm(0.012 - question_exclam_ratio(sentences), 0, 0.012)  # 问句少→分高
    d_num      = _norm(6 - number_density(text), 0, 6)      # 数字少→分高
    d_para     = _norm(para_starter_ratio(text, sentences), 0, 0.5)

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

    # 命中套话的句子（供改写参考）
    hit_sents = []
    for s in sentences:
        hits = [p for p in AI_PHRASES if p in s]
        if hits:
            hit_sents.append({"句子": s[:80], "命中": hits[:4], "命中数": len(hits)})
    hit_sents.sort(key=lambda x: -x["命中数"])

    return score100, details, hit_sents


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        text = f.read()

    total, details, hit_sents = score(text)

    cn = chars_cn(text)
    print("=" * 64)
    print(f"文件：{sys.argv[1]}")
    print(f"中文字数：{len(cn)}　句子数：{details['原始指标']['句数']}")
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
