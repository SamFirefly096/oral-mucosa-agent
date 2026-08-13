"""
v0.1.3 未完成对话审查分析脚本
对 40 例未完成诊断进行逐例审查，分类为：
1. 轮次耗尽 - 对话轮次不足以完成诊断
2. 信息客观不足 - 数据库中的信息不完整
3. 提示词诱导的过度谨慎 - 反思提示导致的不必要放弃
"""
import json
import re
import os
from pathlib import Path
from collections import defaultdict

if hasattr(os, 'name') and os.name == 'nt':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).resolve().parent
CONVERSATIONS_DIR = PROJECT_ROOT / "outputs" / "conversations"
RESULTS_DIR = PROJECT_ROOT / "outputs" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def analyze_incomplete_conversation(filepath: Path) -> dict:
    """审查单个未完成对话"""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    log = data.get("conversation_log", [])
    hadm_id = data.get("hadm_id", "unknown")
    stats = data.get("statistics", {})

    # ── 检查指标 ──
    total_turns = stats.get("total_turns", 0)
    tool_calls = stats.get("tool_calls", 0)
    completed = data.get("completed", False)

    # 统计已执行的工具类型
    tools_used = []
    for entry in log:
        role = entry.get("role", "")
        if role.startswith("Tool("):
            tool_name = role.replace("Tool(", "").replace(")", "")
            tools_used.append(tool_name)

    oral_exam_done = "perform_oral_examination" in tools_used
    tcm_done = "perform_tcm_four_diagnosis" in tools_used
    lab_done = "order_lab_tests" in tools_used
    path_done = "order_pathology" in tools_used
    micro_done = "order_microbiology" in tools_used
    diag_attempted = any("finalize_diagnosis" in t for t in tools_used)
    reflection_triggered = any("reflection" in entry.get("role", "").lower() for entry in log)

    # 计算对话轮次（患者-医生交互）
    patient_turns = sum(1 for e in log if e.get("role") == "PatientAgent")
    doctor_turns = sum(1 for e in log if e.get("role") == "MedAgent" and "reflection" not in e.get("role", "").lower())

    # ── 分析对话内容 ──
    # 检查反思后的行为
    reflection_entries = [e for e in log if "reflection" in e.get("role", "").lower()]
    reflection_content = ""
    reflection_diag_retry = False
    for entry in reflection_entries:
        content = entry.get("content", "")
        reflection_content += content[:500]
        # 检查反思后是否尝试重新诊断
        if "finalize" in content.lower() or "确认无误" in content or "修正" in content:
            reflection_diag_retry = True

    # 检查是否有"放弃"或"无法确定"的表述
    abandonment_phrases = [
        "无法确定", "无法诊断", "信息不足", "不能确定", "放弃",
        "需要更多信息", "目前无法", "暂不", "无法做出", "证据不足",
        "无法完成", "尚不能"
    ]
    found_abandonment = []
    for phrase in abandonment_phrases:
        if phrase in reflection_content:
            found_abandonment.append(phrase)

    # 检查 force_finish 是否被触发
    forced = any("forced" in entry.get("role", "") for entry in log)
    max_turns_reached = forced and not completed

    # ── 分类 ──
    if max_turns_reached:
        if oral_exam_done and tcm_done and lab_done and not diag_attempted:
            root_cause = "轮次耗尽-诊断前耗尽"
            detail = f"完成了检查但对话轮次({total_turns})不足以到达诊断步骤"
        elif oral_exam_done and diag_attempted and not completed:
            root_cause = "轮次耗尽-反思后耗尽"
            detail = f"反思循环消耗额外轮次，反思后轮次不足"
        else:
            root_cause = "轮次耗尽-信息收集阶段耗尽"
            detail = f"在信息收集阶段消耗了所有轮次({total_turns})"
    elif diag_attempted and reflection_triggered and found_abandonment:
        root_cause = "提示词诱导过度谨慎"
        detail = f"反思后出现放弃表述: {found_abandonment}"
    elif diag_attempted and not completed:
        root_cause = "提示词诱导过度谨慎"
        detail = "诊断提交后反思循环未触发后续finalize调用"
    elif not diag_attempted:
        if oral_exam_done and tcm_done:
            root_cause = "信息客观不足"
            detail = "所有常规检查已完成但Agent仍无法形成诊断假设"
        else:
            root_cause = "信息收集不充分"
            detail = f"检查完成度不足: 口腔检查={oral_exam_done}, 四诊={tcm_done}, 化验={lab_done}, 病理={path_done}"
    else:
        root_cause = "其他/待定"
        detail = "需人工审查"

    return {
        "hadm_id": hadm_id,
        "file": filepath.name,
        "completed": completed,
        "total_turns": total_turns,
        "patient_turns": patient_turns,
        "doctor_turns": doctor_turns,
        "tool_calls": tool_calls,
        "tools_used": tools_used,
        "oral_exam": oral_exam_done,
        "tcm": tcm_done,
        "lab": lab_done,
        "pathology": path_done,
        "microbiology": micro_done,
        "diagnosis_attempted": diag_attempted,
        "reflection_triggered": reflection_triggered,
        "reflection_diag_retry": reflection_diag_retry,
        "forced_finish": forced,
        "abandonment_phrases": found_abandonment,
        "root_cause": root_cause,
        "detail": detail,
    }


def run_analysis(conversations_dir: Path = None) -> dict:
    """运行40例未完成对话的审查分析"""
    if conversations_dir is None:
        conversations_dir = CONVERSATIONS_DIR

    if not conversations_dir.exists():
        print(f"目录不存在: {conversations_dir}，尝试查找其他位置...")
        # 尝试查找
        alt_dirs = [
            PROJECT_ROOT / ".." / ".." / "outputs" / "conversations",
            Path("E:/工作目录/口腔黏膜病AI诊断_2026-07-05/输入/oral-mucosa-agent-full/outputs/conversations"),
        ]
        for d in alt_dirs:
            if d.exists():
                conversations_dir = d
                print(f"  找到: {conversations_dir}")
                break
        else:
            return {"error": "未找到对话目录，请手动指定路径"}

    json_files = sorted(conversations_dir.glob("*.json"))
    if not json_files:
        return {"error": f"在 {conversations_dir} 中未找到 JSON 对话文件"}

    # 全量分析
    all_results = []
    for f in json_files:
        try:
            r = analyze_incomplete_conversation(f)
            all_results.append(r)
        except Exception as e:
            print(f"  [SKIP] {f.name}: {e}")

    # 筛选未完成的
    incomplete = [r for r in all_results if not r["completed"]]
    complete = [r for r in all_results if r["completed"]]

    # 按根因分类
    cause_groups = defaultdict(list)
    for r in incomplete:
        cause_groups[r["root_cause"]].append(r)

    # 生成报告
    report_lines = [
        "=" * 70,
        "  口腔黏膜病AI诊断Agent — 未完成对话审查报告 (v0.1.3)",
        "=" * 70,
        "",
        f"审查时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"对话目录: {conversations_dir}",
        f"总对话数: {len(all_results)}",
        f"已完成: {len(complete)} ({len(complete)/len(all_results)*100:.1f}%)",
        f"未完成: {len(incomplete)} ({len(incomplete)/len(all_results)*100:.1f}%)",
        "",
        "── 一、未完成根因分类 ──",
    ]

    for cause, items in sorted(cause_groups.items(), key=lambda x: -len(x[1])):
        report_lines.append(f"\n  【{cause}】{len(items)}例")
        for item in items:
            report_lines.append(
                f"    {item['hadm_id']:<12} | "
                f"轮次{item['total_turns']:>3} | "
                f"工具{item['tool_calls']:>2}次 | "
                f"口腔检查={item['oral_exam']} 四诊={item['tcm']} 化验={item['lab']} 病理={item['pathology']} | "
                f"诊断尝试={item['diagnosis_attempted']} 反思={item['reflection_triggered']}"
            )
            if item.get("abandonment_phrases"):
                report_lines.append(f"              放弃表述: {item['abandonment_phrases']}")
            report_lines.append(f"              → {item['detail']}")

    report_lines.extend([
        "",
        "── 二、已完成对话概况 ──",
        f"  总完成数: {len(complete)}",
        f"  平均轮次: {sum(c['total_turns'] for c in complete)/len(complete):.1f}" if complete else "  N/A",
        f"  平均工具调用: {sum(c['tool_calls'] for c in complete)/len(complete):.1f}" if complete else "  N/A",
        "",
        "── 三、v0.1.3 改进建议 ──",
        "",
        "1. 如果'提示词诱导过度谨慎'占主导 → v0.1.3的置信度分级方案应能显著改善",
        "2. 如果'轮次耗尽'占主导 → 需增加max_turns或优化反思循环不额外消耗轮次",
        "3. 如果'信息客观不足'占主导 → 需补充数据库中的病例信息",
        "",
        "── 四、各病例详细数据 ──",
    ])

    for r in sorted(all_results, key=lambda x: x["hadm_id"]):
        status = "[OK]" if r["completed"] else "[X]"
        report_lines.append(
            f"  {status} {r['hadm_id']:<12} | 轮次{r['total_turns']:>3} | "
            f"工具{r['tool_calls']:>2} | "
            f"口检={r['oral_exam']} 四诊={r['tcm']} 化验={r['lab']} 病理={r['pathology']} | "
            f"诊断={r['diagnosis_attempted']} 反思={r['reflection_triggered']}"
        )

    report_text = "\n".join(report_lines)

    return {
        "report": report_text,
        "incomplete": incomplete,
        "complete": complete,
        "cause_groups": {k: [r["hadm_id"] for r in v] for k, v in cause_groups.items()},
        "summary": {
            "total": len(all_results),
            "complete": len(complete),
            "incomplete": len(incomplete),
            "cause_counts": {k: len(v) for k, v in cause_groups.items()},
        },
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="未完成对话审查分析")
    parser.add_argument("--dir", type=str, default=None, help="对话目录路径")
    args = parser.parse_args()

    conv_dir = Path(args.dir) if args.dir else None
    result = run_analysis(conv_dir)

    if "error" in result:
        print(result["error"])
    else:
        print(result["report"])

        # 保存
        report_path = RESULTS_DIR / "incomplete_analysis_v013.txt"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(result["report"])
        print(f"\n报告已保存: {report_path}")

        json_path = RESULTS_DIR / "incomplete_analysis_v013.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({
                "summary": result["summary"],
                "cause_groups": result["cause_groups"],
            }, f, ensure_ascii=False, indent=2)
        print(f"数据已保存: {json_path}")
