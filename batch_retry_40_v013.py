#!/usr/bin/env python3
"""
v0.1.3 重跑v0.1.2的40例未完成病例
使用 conversation_v013 (知识库检索锚定 + 改进反思提示词)
3路并行：Group A (Learn), Group B (Textbook), Group C (Chief)
"""
import sys, os, time, json
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT_ROOT = Path('/opt/oral-mucosa-agent')
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))
os.environ['MIRA_ENABLE_THINKING'] = 'false'

from database import get_hpi_text, query_table
from agents_enhanced import (
    LearningMedAgent, TextbookMedAgent, ChiefMedAgent,
    OriginalPatientAgent, RealisticPatientAgent, PatientContext
)
from conversation_v013 import run_conversation, save_result
from config import SAVE_DIR, MEDICAL_MODEL, PATIENT_MODEL

# 40个v0.1.2未完成病例（从retry_40记录中提取）
FAILED_CASES = {
    "Learn_Original":    ["DLE001", "ROM001", "AOU001", "MRAS001", "OLL001"],
    "Learn_Realistic":   ["OLP001", "AOU001", "MRAS001", "PIM001", "MRS001"],
    "Textbook_Original": ["ROM001", "AOU001", "MRAS001", "WSN001", "CC001", "PIM001", "MRS001"],
    "Textbook_Realistic":["LR001", "ATOLP001", "ROM001", "LEUK002", "AOU001", "MRAS001", "OLL001", "CC001"],
    "Chief_Original":    ["ATOLP001", "MRAS001", "OLL001", "PIM001"],
    "Chief_Realistic":   ["RAS001", "DLE001", "EM001", "LR001", "ROM001", "LEUK002", "HZ001", "AOU001", "MRAS001", "PIM001", "MRS001"],
}

AGENT_CLASS = {
    "Learn":    LearningMedAgent,
    "Textbook": TextbookMedAgent,
    "Chief":    ChiefMedAgent,
}

PATIENT_CLASS = {
    "Original":  OriginalPatientAgent,
    "Realistic": RealisticPatientAgent,
}


def run_one(hadm_id, med_type, pat_type):
    """Run a single case with v0.1.3"""
    try:
        cc = query_table('chief_complaints', hadm_id)
        patient = query_table('patients', hadm_id)
        if not cc or not patient:
            return {"hadm_id": hadm_id, "error": "no_data"}

        hpi = get_hpi_text(hadm_id)
        ctx = PatientContext(
            hadm_id=hadm_id,
            patient_info_text=hpi,
            age=patient.get('age'),
            gender=patient.get('gender'),
        )

        med = AGENT_CLASS[med_type](model=MEDICAL_MODEL, thinking=False)
        pat = PATIENT_CLASS[pat_type](model=PATIENT_MODEL)
        pat.init_with_patient(ctx)

        t0 = time.time()
        result = run_conversation(
            med_agent=med,
            patient_agent=pat,
            patient_context=ctx,
            primary_complaint='',
            max_turns=40,
            verbose=False,
        )
        elapsed = time.time() - t0

        # 保存结果
        label = f"{med_type}_{pat_type}"
        ts = time.strftime('%Y%m%d_%H%M%S')
        filename = f"{hadm_id}_{label}_{ts}.json"
        filepath = SAVE_DIR / filename
        output = {
            "hadm_id": hadm_id,
            "label": label,
            "conversation_log": result.get("conversation_log", []),
            "statistics": result.get("statistics", {}),
            "completed": result.get("completed", False),
            "version": result.get("version", "v0.1.3"),
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        return {
            "hadm_id": hadm_id,
            "med_type": med_type,
            "pat_type": pat_type,
            "completed": result.get("completed", False),
            "turns": result.get("statistics", {}).get("total_turns", 0),
            "tools": result.get("statistics", {}).get("tool_calls", 0),
            "time": round(elapsed, 0),
            "version": result.get("version", ""),
            "save_path": str(filepath),
        }
    except Exception as e:
        return {"hadm_id": hadm_id, "med_type": med_type, "pat_type": pat_type, "error": str(e)}


def main():
    print(f"v0.1.3 重跑40例未完成病例")
    print(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"并行数: 3 workers")
    print("=" * 60)

    # 构建任务列表
    tasks = []
    for group, case_ids in FAILED_CASES.items():
        parts = group.split("_")
        med_type = parts[0]  # Learn/Textbook/Chief
        pat_type = parts[1]  # Original/Realistic
        for hadm_id in case_ids:
            tasks.append((hadm_id, med_type, pat_type))

    print(f"总任务数: {len(tasks)}")
    sys.stdout.flush()

    results = []
    t_start = time.time()

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(run_one, hadm_id, med_type, pat_type): (hadm_id, med_type, pat_type)
            for hadm_id, med_type, pat_type in tasks
        }

        for i, future in enumerate(as_completed(futures), 1):
            hadm_id, med_type, pat_type = futures[future]
            try:
                r = future.result()
                results.append(r)
                status = "[OK]" if r.get("completed") else "[X]"
                err = f" ERROR: {r['error']}" if r.get('error') else ""
                print(f"[{i}/{len(tasks)}] {status} {med_type}x{pat_type} {hadm_id} | "
                      f"turns={r.get('turns', '?')} tools={r.get('tools', '?')} "
                      f"time={r.get('time', 0):.0f}s{err}")
                sys.stdout.flush()
            except Exception as e:
                results.append({"hadm_id": hadm_id, "error": str(e)})
                print(f"[{i}/{len(tasks)}] [X] {hadm_id} EXCEPTION: {e}")
                sys.stdout.flush()

    elapsed = time.time() - t_start

    # 汇总
    completed = [r for r in results if r.get("completed")]
    failed = [r for r in results if not r.get("completed") or r.get("error")]

    print(f"\n{'='*60}")
    print(f"v0.1.3 重跑完成")
    print(f"  总任务: {len(tasks)}")
    print(f"  完成: {len(completed)} ({len(completed)/max(len(tasks), 1)*100:.1f}%)")
    print(f"  未完成: {len(failed)} ({len(failed)/max(len(tasks), 1)*100:.1f}%)")
    print(f"  总耗时: {elapsed/60:.1f}分钟")
    print(f"{'='*60}")
    sys.stdout.flush()

    # 保存结果JSON
    result_path = Path('/opt/oral-mucosa-agent/outputs/results/retry_40_v013_results.json')
    result_path.parent.mkdir(parents=True, exist_ok=True)
    with open(result_path, 'w', encoding='utf-8') as f:
        json.dump({
            "version": "v0.1.3",
            "timestamp": datetime.now().isoformat(),
            "total": len(tasks),
            "completed": len(completed),
            "incomplete": len(failed),
            "elapsed_minutes": round(elapsed / 60, 1),
            "results": results,
        }, f, ensure_ascii=False, indent=2)

    print(f"结果已保存: {result_path}")

    # 打印未完成列表
    if failed:
        print(f"\n未完成病例:")
        for r in failed:
            err = r.get('error', '')
            print(f"  {r['hadm_id']} ({r.get('med_type', '?')}x{r.get('pat_type', '?')}): {err}")


if __name__ == "__main__":
    main()
