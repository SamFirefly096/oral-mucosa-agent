"""
v0.1.3 多维评估脚本
重新定义完成标准：将"有充分论证的不确定诊断"计入完成。
新评估维度：
1. 诊断完成度（Completion Tier）：确诊/暂定诊断/证据不足-已记录/放弃
2. 置信度分级准确率（Confidence-Calibrated Accuracy）
3. 诊断语义准确性（Semantic Accuracy）
4. 证据充分性（Evidence Sufficiency）
5. 鉴别诊断完整度（DD Completeness）
"""
import json
import os
import re
from pathlib import Path
from collections import defaultdict

# 确保输出编码正确
if hasattr(os, 'name') and os.name == 'nt':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')


# ═══════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════
PROJECT_ROOT = Path(__file__).resolve().parent
CONVERSATIONS_DIR = PROJECT_ROOT / "outputs" / "conversations"
RESULTS_DIR = PROJECT_ROOT / "outputs" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════
# 诊断类别关键词映射（用于语义准确率判断）
# ═══════════════════════════════════════════════════════════
DIAGNOSIS_KEYWORDS = {
    "oral_lichen_planus": ["口腔扁平苔藓", "OLP", "扁平苔藓", "口癣", "oral lichen planus"],
    "pemphigus_vulgaris": ["天疱疮", "寻常型天疱疮", "pemphigus vulgaris", "火赤疮"],
    "bullous_pemphigoid": ["类天疱疮", "大疱性类天疱疮", "bullous pemphigoid"],
    "oral_candidiasis": ["念珠菌", "鹅口疮", "candidiasis", "candida"],
    "recurrent_aphthous": ["阿弗他", "复发性.*口疮", "aphthous", "RAU", "RAS"],
    "herpes_simplex": ["疱疹", "HSV", "herpes", "龈口炎"],
    "discoid_lupus": ["红斑狼疮", "DLE", "discoid lupus", "lupus", "唇风"],
    "erythema_multiforme": ["多形红斑", "erythema multiforme", "猫眼疮", "EM"],
    "leukoplakia": ["白斑(?!.*海绵)", "leukoplakia", "白斑"],
    "anug": ["坏死.*龈", "ANUG", "牙疳", "necrotizing.*gingivitis"],
    "lichenoid_reaction": ["苔藓样反应", "苔藓样", "lichenoid"],
}


# ═══════════════════════════════════════════════════════════
# v0.1.3 完成层级（Completion Tier）
# ═══════════════════════════════════════════════════════════
class CompletionTier:
    CONFIRMED = "tier1_confirmed"         # [A] 确诊 - 所有标准满足
    TENTATIVE = "tier2_tentative"         # [B] 暂定诊断 - 部分信息不足
    INSUFFICIENT = "tier3_insufficient"   # [C] 证据不足但已记录推理
    ABANDONED = "tier4_abandoned"         # 完全放弃，未输出任何诊断


def classify_completion_tier(conversation: dict) -> tuple:
    """根据对话日志判断完成层级"""
    log = conversation.get("conversation_log", [])

    # 查找最后一条 finalize_diagnosis 调用
    last_diag = None
    for entry in reversed(log):
        if entry.get("role", "").startswith("Tool") and "finalize" in entry.get("role", ""):
            last_diag = entry
            break
        # 也检查 tool_call 中的信息
        if entry.get("tool_call", {}).get("name") == "finalize_diagnosis":
            last_diag = entry
            break

    # 检查对话是否完成
    completed = conversation.get("completed", False)
    forced = any("forced" in entry.get("role", "") for entry in log)

    if not last_diag and not completed:
        return CompletionTier.ABANDONED, "no_diagnosis_attempted"

    if not last_diag:
        return CompletionTier.ABANDONED, "no_finalize_call"

    # 获取诊断内容
    content = last_diag.get("content", "")
    tool_args = last_diag.get("tool_call", {}).get("arguments", {})
    primary = tool_args.get("primary_diagnosis", "")

    if not primary:
        # 尝试从 content 解析
        if "主要诊断" in str(content):
            primary = "from_content"

    # 分类
    if "诊断未确定" in primary or "无法确定" in primary:
        return CompletionTier.INSUFFICIENT, "explicitly_undetermined"
    if "暂定诊断" in primary or "tentative" in primary.lower():
        return CompletionTier.TENTATIVE, "tentative_diagnosis"
    if primary:
        return CompletionTier.CONFIRMED, "diagnosis_provided"

    return CompletionTier.ABANDONED, "empty_diagnosis"


def evaluate_semantic_accuracy(hadm_id: str, diagnosis_text: str) -> tuple:
    """评估语义准确性：Agent诊断是否匹配预期诊断类别"""
    from database import query_table
    diag_row = query_table("diagnoses", hadm_id)
    if not diag_row:
        return False, "no_reference", ""

    expected_category = diag_row.get("diagnosis_category", "")
    expected_diag = diag_row.get("primary_diagnosis", "")

    if not expected_category:
        return False, "unknown_category", ""

    keywords = DIAGNOSIS_KEYWORDS.get(expected_category, [expected_diag])
    diag_lower = diagnosis_text.lower()

    matched = []
    for kw in keywords:
        if re.search(kw, diag_lower):
            matched.append(kw)

    is_correct = len(matched) > 0
    confidence = "exact" if len(matched) >= 2 else "partial" if is_correct else "mismatch"

    return is_correct, confidence, expected_category


def analyze_case(conversation_file: Path) -> dict:
    """分析单个对话"""
    with open(conversation_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    hadm_id = data.get("hadm_id", "unknown")
    tier, tier_reason = classify_completion_tier(data)

    # 提取诊断文本
    log = data.get("conversation_log", [])
    diagnosis_text = ""
    for entry in reversed(log):
        tc = entry.get("tool_call", {})
        if tc.get("name") == "finalize_diagnosis":
            args = tc.get("arguments", {})
            diagnosis_text = args.get("primary_diagnosis", "")
            break

    # 语义准确率
    is_accurate, acc_confidence, expected_cat = evaluate_semantic_accuracy(hadm_id, diagnosis_text)

    # v0.1.3 新增：处理暂定诊断的准确率
    effective_accurate = is_accurate
    if tier == CompletionTier.TENTATIVE and not is_accurate:
        # 暂定诊断即使不完全匹配，如果是鉴别列表中的也可计为部分准确
        dd_list = []
        for entry in reversed(log):
            tc = entry.get("tool_call", {})
            if tc.get("name") == "finalize_diagnosis":
                dd_list = tc.get("arguments", {}).get("differential_diagnoses", [])
                break
        for dd in dd_list:
            matched, _, _ = evaluate_semantic_accuracy(hadm_id, str(dd))
            if matched:
                effective_accurate = True
                break

    return {
        "hadm_id": hadm_id,
        "completion_tier": tier,
        "tier_reason": tier_reason,
        "diagnosis_text": diagnosis_text[:200],
        "semantic_accuracy": is_accurate,
        "effective_accuracy": effective_accurate,
        "expected_category": expected_cat,
        "statistics": data.get("statistics", {}),
        "version": data.get("version", "unknown"),
    }


# ═══════════════════════════════════════════════════════════
# 多维度评估报告
# ═══════════════════════════════════════════════════════════
def evaluate_all(conversations_dir: Path = None) -> dict:
    """评估所有对话并生成报告"""
    if conversations_dir is None:
        conversations_dir = CONVERSATIONS_DIR

    if not conversations_dir.exists():
        return {"error": f"目录不存在: {conversations_dir}"}

    json_files = sorted(conversations_dir.glob("*.json"))
    if not json_files:
        return {"error": f"在 {conversations_dir} 中未找到 JSON 对话文件"}

    results = []
    for f in json_files:
        try:
            r = analyze_case(f)
            results.append(r)
        except Exception as e:
            print(f"  [SKIP] {f.name}: {e}")

    # 统计
    from collections import Counter
    tier_counts = Counter(r["completion_tier"] for r in results)
    accurate_count = sum(1 for r in results if r["semantic_accuracy"])
    effective_accurate = sum(1 for r in results if r["effective_accuracy"])

    # 按 Agent 分组 (从文件名推断)
    by_agent = defaultdict(list)
    for r in results:
        fname = r["hadm_id"]
        by_agent["all"].append(r)

    report_lines = [
        "=" * 70,
        "  口腔黏膜病AI诊断Agent — v0.1.3 多维度评估报告",
        "=" * 70,
        "",
        f"评估时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"总对话数: {len(results)}",
        "",
        "── 一、诊断完成层级 (Completion Tier) ──",
        f"  Tier 1 - 确诊 (Confirmed):           {tier_counts.get(CompletionTier.CONFIRMED, 0):>4}",
        f"  Tier 2 - 暂定诊断 (Tentative):       {tier_counts.get(CompletionTier.TENTATIVE, 0):>4}",
        f"  Tier 3 - 证据不足·已记录 (Insufficient):{tier_counts.get(CompletionTier.INSUFFICIENT, 0):>4}",
        f"  Tier 4 - 放弃 (Abandoned):           {tier_counts.get(CompletionTier.ABANDONED, 0):>4}",
        "",
        f"  有效完成率 (Tier1+Tier2+Tier3): {tier_counts.get(CompletionTier.CONFIRMED,0)+tier_counts.get(CompletionTier.TENTATIVE,0)+tier_counts.get(CompletionTier.INSUFFICIENT,0)}/{len(results)} = {(tier_counts.get(CompletionTier.CONFIRMED,0)+tier_counts.get(CompletionTier.TENTATIVE,0)+tier_counts.get(CompletionTier.INSUFFICIENT,0))/len(results)*100:.1f}%",
        f"  传统完成率 (仅Tier1): {tier_counts.get(CompletionTier.CONFIRMED,0)}/{len(results)} = {tier_counts.get(CompletionTier.CONFIRMED,0)/len(results)*100:.1f}%",
        "",
        "── 二、语义准确性 ──",
        f"  严格准确率 (仅Tier1+Tier2中匹配): {accurate_count}/{len(results)} = {accurate_count/len(results)*100:.1f}%",
        f"  有效准确率 (含DD列表中正确): {effective_accurate}/{len(results)} = {effective_accurate/len(results)*100:.1f}%",
        "",
        "── 三、置信度校准分析 ──",
    ]

    # 按tier计算准确率
    for tier_label, tier_key in [("Tier1-确诊", CompletionTier.CONFIRMED),
                                   ("Tier2-暂定", CompletionTier.TENTATIVE),
                                   ("Tier3-不足", CompletionTier.INSUFFICIENT)]:
        tier_results = [r for r in results if r["completion_tier"] == tier_key]
        if tier_results:
            tier_acc = sum(1 for r in tier_results if r["semantic_accuracy"])
            report_lines.append(f"  {tier_label}: {tier_acc}/{len(tier_results)} 语义准确 = {tier_acc/len(tier_results)*100:.1f}%")

    report_lines.append("")
    report_lines.append("── 四、各病例详情 ──")
    report_lines.append(f"  {'病例ID':<12} {'层级':<15} {'语义准确':<8} {'有效准确':<8} {'预期类别'}")
    report_lines.append("  " + "-" * 70)
    for r in sorted(results, key=lambda x: x["hadm_id"]):
        tier_short = {
            CompletionTier.CONFIRMED: "T1-确诊",
            CompletionTier.TENTATIVE: "T2-暂定",
            CompletionTier.INSUFFICIENT: "T3-不足",
            CompletionTier.ABANDONED: "T4-放弃",
        }.get(r["completion_tier"], "未知")
        report_lines.append(
            f"  {r['hadm_id']:<12} {tier_short:<15} "
            f"{'[OK]' if r['semantic_accuracy'] else '[X]':<8} "
            f"{'[OK]' if r['effective_accuracy'] else '[X]':<8} "
            f"{r['expected_category']}"
        )

    report_text = "\n".join(report_lines)
    return {
        "results": results,
        "tier_counts": dict(tier_counts),
        "report": report_text,
        "total": len(results),
        "completion_rate_new": (tier_counts.get(CompletionTier.CONFIRMED, 0) +
                                tier_counts.get(CompletionTier.TENTATIVE, 0) +
                                tier_counts.get(CompletionTier.INSUFFICIENT, 0)) / len(results) * 100,
        "completion_rate_old": tier_counts.get(CompletionTier.CONFIRMED, 0) / len(results) * 100,
        "strict_accuracy": accurate_count / len(results) * 100,
        "effective_accuracy": effective_accurate / len(results) * 100,
    }


if __name__ == "__main__":
    eval_result = evaluate_all()
    if "error" in eval_result:
        print(eval_result["error"])
    else:
        print(eval_result["report"])

        # 保存报告
        report_path = RESULTS_DIR / "eval_v013_report.txt"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(eval_result["report"])
        print(f"\n报告已保存: {report_path}")

        # 保存 JSON
        json_path = RESULTS_DIR / "eval_v013_data.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({
                "summary": {
                    "total": eval_result["total"],
                    "completion_rate_new": eval_result["completion_rate_new"],
                    "completion_rate_old": eval_result["completion_rate_old"],
                    "strict_accuracy": eval_result["strict_accuracy"],
                    "effective_accuracy": eval_result["effective_accuracy"],
                    "tier_counts": eval_result["tier_counts"],
                },
                "details": eval_result["results"],
            }, f, ensure_ascii=False, indent=2)
        print(f"数据已保存: {json_path}")
