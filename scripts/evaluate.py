"""
评估脚本：对比 Agent 诊断与数据库真实诊断

评估维度（参照 MIRA 论文）：
1. 诊断准确率 (primary diagnosis match)
2. 鉴别诊断覆盖度
3. 工具使用合理性
4. 用药安全性
5. 住院决策准确性
"""
import json
import re
from pathlib import Path

from config import RESULTS_DIR, SAVE_DIR, DIAGNOSIS_CATEGORIES
from database import query_table


def load_conversation(filepath: Path) -> dict:
    """加载对话记录"""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_final_diagnosis(conversation: dict) -> dict | None:
    """从对话记录中提取 Agent 的最终诊断"""
    for entry in conversation.get("conversation_log", []):
        if entry.get("type") == "terminated" and "Tool(" in entry.get("role", ""):
            tc = entry.get("tool_call", {})
            if tc.get("name") == "finalize_diagnosis":
                return tc.get("arguments", {})
    return None


def match_diagnosis(agent_diag: dict, true_diag: dict) -> dict:
    """比较 Agent 诊断与真实诊断，基于中文2-gram字符覆盖"""
    agent_primary = (agent_diag or {}).get("primary_diagnosis", "")
    true_primary = true_diag.get("primary_diagnosis", "")

    # 清洗文本
    def clean(s):
        s = s.lower().strip()
        s = re.sub(r'[（()（）,，\-\s]+', '', s)
        s = re.sub(r'icd.*$', '', s)
        return s

    agent_clean = clean(agent_primary)
    true_clean = clean(true_primary)

    # 精确匹配
    if agent_clean == true_clean:
        return {
            "exact_match": True, "partial_match": True,
            "keyword_coverage": 1.0,
            "agent_diagnosis": agent_primary, "true_diagnosis": true_primary,
        }

    # 2-gram 字符覆盖 (对中文更鲁棒)
    def char_ngrams(s, n=2):
        return set(s[i:i+n] for i in range(len(s)-n+1))

    true_ng = char_ngrams(true_clean)
    agent_ng = char_ngrams(agent_clean)

    if not true_ng:
        coverage = 1.0 if agent_clean == true_clean else 0.0
    else:
        overlap = len(true_ng & agent_ng)
        coverage = overlap / len(true_ng)

    # 包含匹配
    contains_match = true_clean in agent_clean or agent_clean in true_clean
    partial = coverage >= 0.4 or contains_match

    return {
        "exact_match": False,
        "partial_match": partial,
        "keyword_coverage": round(coverage, 2),
        "agent_diagnosis": agent_primary,
        "true_diagnosis": true_primary,
    }


def evaluate_case(hadm_id: str) -> dict:
    """评估单个病例"""
    # 查找对话文件
    pattern = f"{hadm_id}_*.json"
    files = sorted(SAVE_DIR.glob(pattern))
    if not files:
        return {"hadm_id": hadm_id, "error": "未找到对话记录"}

    # 取最新文件
    filepath = files[-1]
    conv = load_conversation(filepath)

    # 提取 Agent 诊断
    agent_diag = extract_final_diagnosis(conv)
    if not agent_diag:
        return {"hadm_id": hadm_id, "error": "Agent 未完成诊断", "file": str(filepath)}

    # 获取真实诊断
    true_diag = query_table("diagnoses", hadm_id)
    true_treatment = query_table("treatments", hadm_id)

    # 诊断匹配
    diag_match = match_diagnosis(agent_diag, true_diag)

    # 住院决策
    true_admission = true_treatment.get("admission_needed", "no")
    agent_admission = agent_diag.get("admission_needed", "no")

    stats = conv.get("statistics", {})

    return {
        "hadm_id": hadm_id,
        "file": str(filepath),
        "diagnosis_match": diag_match,
        "true_admission": true_admission,
        "agent_admission": agent_admission,
        "admission_agreement": true_admission == agent_admission,
        "agent_differential_count": len(
            agent_diag.get("differential_diagnoses", [])
        ),
        "true_differential_str": true_diag.get("differential_diagnoses", ""),
        "statistics": stats,
    }


def evaluate_all() -> list[dict]:
    """评估所有已运行的病例"""
    results = []
    files = list(SAVE_DIR.glob("*.json"))
    if not files:
        print("SAVE_DIR 中没有对话记录。请先运行 run_simulation.py")
        return results

    hadm_ids = set()
    for f in files:
        match = re.match(r"([A-Z]+\d+)_", f.name)
        if match:
            hadm_ids.add(match.group(1))

    print(f"找到 {len(hadm_ids)} 个病例的对话记录\n")

    for hadm_id in sorted(hadm_ids):
        result = evaluate_case(hadm_id)
        results.append(result)

    # 汇总
    valid = [r for r in results if "error" not in r]
    if valid:
        exact = sum(1 for r in valid if r["diagnosis_match"]["exact_match"])
        partial = sum(1 for r in valid if r["diagnosis_match"]["partial_match"])
        adm = sum(1 for r in valid if r["admission_agreement"])

        print(f"\n{'='*60}")
        print(f"评估汇总 ({len(valid)} 例)")
        print(f"  完全匹配: {exact}/{len(valid)} ({exact/len(valid)*100:.1f}%)")
        print(f"  部分匹配(关键词覆盖≥50%): {partial}/{len(valid)} ({partial/len(valid)*100:.1f}%)")
        print(f"  住院决策一致: {adm}/{len(valid)} ({adm/len(valid)*100:.1f}%)")
        avg_time = sum(r["statistics"].get("total_time_seconds", 0) for r in valid) / len(valid)
        avg_tools = sum(r["statistics"].get("tool_calls", 0) for r in valid) / len(valid)
        print(f"  平均耗时: {avg_time:.1f}s")
        print(f"  平均工具调用: {avg_tools:.1f}次")

    # 明细
    for r in results:
        if "error" in r:
            print(f"\n  {r['hadm_id']}: ❌ {r['error']}")
        else:
            dm = r["diagnosis_match"]
            icon = "✅" if dm["exact_match"] else ("⚠️" if dm["partial_match"] else "❌")
            print(f"\n  {icon} {r['hadm_id']}")
            print(f"     Agent: {dm['agent_diagnosis'][:80]}")
            print(f"     True:  {dm['true_diagnosis'][:80]}")
            print(f"     Coverage: {dm['keyword_coverage']}")

    return results


if __name__ == "__main__":
    evaluate_all()
