"""
运行入口：口腔黏膜病 AI Agent 模拟诊断

用法：
    # 单病例交互式运行
    python run_simulation.py --case OLP001

    # 运行多个病例
    python run_simulation.py --cases OLP001,PV001,OC001

    # 运行所有病例
    python run_simulation.py --all

    # 安静模式（只输出统计）
    python run_simulation.py --case OLP001 --quiet
"""
import argparse
import sys
from pathlib import Path

# 确保项目路径
sys.path.insert(0, str(Path(__file__).resolve().parent))

# 强制 stdout 使用 UTF-8 编码（Windows GBK 兼容）
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from database import create_database, get_hpi_text, list_cases, query_table
from agents import MedAssistant, PatientAssistant, PatientContext
from conversation import run_conversation, save_result


def run_single_case(hadm_id: str, verbose: bool = True) -> dict:
    """运行单个病例的完整诊断流程"""
    # 获取数据
    cc = query_table("chief_complaints", hadm_id)
    patient = query_table("patients", hadm_id)
    if not cc or not patient:
        print(f"错误：未找到病例 {hadm_id}")
        return None

    # 准备患者 Context
    hpi_text = get_hpi_text(hadm_id)
    ctx = PatientContext(
        hadm_id=hadm_id,
        patient_info_text=hpi_text,
        age=patient.get("age"),
        gender=patient.get("gender"),
    )

    primary_complaint = cc.get("chief_complaint", "")

    # 初始化 Agent
    med_agent = MedAssistant()
    patient_agent = PatientAssistant()
    patient_agent.init_with_patient(ctx)

    # 运行对话
    result = run_conversation(
        med_agent=med_agent,
        patient_agent=patient_agent,
        patient_context=ctx,
        primary_complaint=primary_complaint,
        verbose=verbose,
    )

    # 保存结果
    save_result(result, hadm_id)

    # 打印统计
    stats = result["statistics"]
    print(f"\n{'='*60}")
    print(f"统计: {hadm_id}")
    print(f"  总耗时: {stats['total_time_seconds']}s")
    print(f"  对话轮次: {stats['total_turns']}")
    print(f"  工具调用: {stats['tool_calls']}次")
    print(f"  MedAgent API 耗时: {stats['med_api_time']}s")
    print(f"  PatientAgent API 耗时: {stats['patient_api_time']}s")
    print(f"  完成状态: {'[OK] 完成' if result['completed'] else '[FAIL] 未完成'}")
    print(f"{'='*60}")

    return result


def main():
    parser = argparse.ArgumentParser(description="口腔黏膜病 AI Agent 模拟诊断")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--case", type=str, help="单个病例ID")
    group.add_argument("--cases", type=str, help="多个病例ID (逗号分隔)")
    group.add_argument("--all", action="store_true", help="运行所有病例")
    group.add_argument("--list", action="store_true", help="列出所有病例")
    parser.add_argument("--quiet", action="store_true", help="安静模式")
    parser.add_argument("--init-db", action="store_true", help="初始化数据库")

    args = parser.parse_args()

    # 初始化数据库
    if args.init_db:
        create_database()
        print("数据库已初始化。")

    # 列出病例
    if args.list:
        print("\n可用的口腔黏膜病病例:\n")
        print(f"{'ID':<12} {'年龄':<6} {'性别':<6} {'诊断'}")
        print("-" * 80)
        for row in list_cases():
            print(f"{row[0]:<12} {row[1]}岁   {'女' if row[2]=='F' else '男':<6} {row[3]}")
        return

    # 确保数据库存在
    if not Path(__file__).resolve().parent.joinpath("data", "oral_mucosa.db").exists():
        print("数据库不存在，正在创建...")
        create_database()

    # 确定要运行的病例
    if args.case:
        case_ids = [args.case]
    elif args.cases:
        case_ids = [c.strip() for c in args.cases.split(",")]
    elif args.all:
        case_ids = [row[0] for row in list_cases()]
    else:
        case_ids = []

    if not case_ids:
        print("未指定病例。使用 --case, --cases, 或 --all")
        return

    verbose = not args.quiet

    # 运行
    results = []
    for i, hadm_id in enumerate(case_ids, 1):
        print(f"\n{'#'*60}")
        print(f"# [{i}/{len(case_ids)}] 病例: {hadm_id}")
        print(f"{'#'*60}")
        try:
            result = run_single_case(hadm_id, verbose=verbose)
            if result:
                results.append(result)
        except Exception as e:
            print(f"[FAIL] {hadm_id} 运行失败: {e}")
            import traceback
            traceback.print_exc()

    # 汇总
    print(f"\n{'='*60}")
    print(f"汇总: {len(results)}/{len(case_ids)} 病例运行完成")
    if results:
        avg_time = sum(r['statistics']['total_time_seconds'] for r in results) / len(results)
        avg_tools = sum(r['statistics']['tool_calls'] for r in results) / len(results)
        print(f"  平均耗时: {avg_time:.1f}s")
        print(f"  平均工具调用: {avg_tools:.1f}次")
        print(f"  完成率: {sum(1 for r in results if r['completed'])}/{len(results)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
