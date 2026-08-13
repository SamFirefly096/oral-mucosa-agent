"""
v0.1.4 DGIC 全量批量运行脚本
24病例 × 6组合 = 144次实验，3路并行
"""
import sys, os, json, time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

PROJECT_ROOT = "/opt/oral-mucosa-agent"
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from config import SAVE_DIR, MEDICAL_MODEL, PATIENT_MODEL
from conversation_v014 import run_conversation, save_result
from agents_enhanced import (
    LearningMedAgent, TextbookMedAgent, ChiefMedAgent,
    OriginalPatientAgent, RealisticPatientAgent, PatientContext,
)
from database import query_table, get_hpi_text, list_cases

write_lock = threading.Lock()

def load_patient(hadm_id: str):
    p = query_table("patients", hadm_id)
    if not p:
        raise ValueError(f"病例 {hadm_id} 不存在")
    cc = query_table("chief_complaints", hadm_id)
    hpi = get_hpi_text(hadm_id) or ""
    info_parts = [hpi]
    safe_tables = ['oral_examinations', 'lab_results', 'microbiology_results', 'pathology_results']
    for table in safe_tables:
        row = query_table(table, hadm_id)
        if row:
            fields = {k: v for k, v in row.items()
                     if k not in ('id', 'hadm_id') and v is not None and v != ''}
            if fields:
                info_parts.append(f"{table}: {json.dumps(fields, ensure_ascii=False)}")
    patient_info = "\n".join(info_parts)
    complaint = cc.get('chief_complaint', '') if cc else ''
    if not complaint and hpi:
        complaint = hpi.split('。')[0] if '。' in hpi else hpi[:100]
    return PatientContext(hadm_id=hadm_id, patient_info_text=patient_info,
                          age=p.get('age'), gender=p.get('gender', '')), complaint


def get_all_cases():
    cases = list_cases()
    return [c[0] for c in cases]


def run_one(hadm_id: str, med_type: str, pat_type: str, patient_ctx, complaint):
    label = f"{hadm_id}_{med_type}_{pat_type}"
    try:
        if med_type == "Learn":
            med = LearningMedAgent(model=MEDICAL_MODEL, thinking=False)
        elif med_type == "Textbook":
            med = TextbookMedAgent(model=MEDICAL_MODEL, thinking=False)
        else:
            med = ChiefMedAgent(model=MEDICAL_MODEL, thinking=False)

        if pat_type == "Original":
            pat = OriginalPatientAgent(model=PATIENT_MODEL)
        else:
            pat = RealisticPatientAgent(model=PATIENT_MODEL)

        pat.init_with_patient(patient_ctx)
        result = run_conversation(med_agent=med, patient_agent=pat,
            patient_context=patient_ctx, primary_complaint=complaint,
            max_turns=30, verbose=False)

        result["label"] = label
        result["model"] = MEDICAL_MODEL
        result["timestamp"] = datetime.now().isoformat()
        filepath = save_result(result, hadm_id, label)
        stats = result["statistics"]
        return {
            "label": label, "hadm_id": hadm_id,
            "completed": result["completed"],
            "turns": stats["total_turns"],
            "tool_calls": stats["tool_calls"],
            "time_seconds": stats["total_time_seconds"],
            "file": str(filepath), "error": None,
        }
    except Exception as e:
        import traceback
        return {"label": label, "hadm_id": hadm_id, "completed": False,
                "turns": 0, "tool_calls": 0, "time_seconds": 0,
                "file": None, "error": str(e)[:200]}


def main():
    cases = get_all_cases()
    combos = [
        ("Learn", "Original"), ("Learn", "Realistic"),
        ("Textbook", "Original"), ("Textbook", "Realistic"),
        ("Chief", "Original"), ("Chief", "Realistic"),
    ]
    total = len(cases) * len(combos)

    print(f"v0.1.4 DGIC 全量批量运行")
    print(f"病例数: {len(cases)}, 组合数: {len(combos)}, 总计: {total}")
    print(f"模型: MED={MEDICAL_MODEL}, PAT={PATIENT_MODEL}")
    print(f"并行度: 3, max_turns: 30")
    print(f"开始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    # 预加载所有患者
    patient_cache = {}
    for cid in cases:
        try:
            patient_cache[cid] = load_patient(cid)
        except Exception as e:
            print(f"  [SKIP] {cid}: {e}")

    # 构建任务列表
    tasks = []
    for cid in cases:
        if cid not in patient_cache:
            continue
        ctx, complaint = patient_cache[cid]
        for med_type, pat_type in combos:
            tasks.append((cid, med_type, pat_type, ctx, complaint))

    results = []
    completed_count = 0
    failed_count = 0
    t_start = time.time()

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(run_one, *t): t for t in tasks}
        for future in as_completed(futures):
            r = future.result()
            results.append(r)
            if r["completed"]:
                completed_count += 1
            else:
                failed_count += 1
            elapsed = time.time() - t_start
            rate = len(results) / (elapsed / 3600) if elapsed > 0 else 0
            with write_lock:
                print(f"[{len(results)}/{len(tasks)}] {r['label']:<35} {'OK' if r['completed'] else 'FAIL'} turns={r['turns']} tools={r['tool_calls']} time={r['time_seconds']:.0f}s | {rate:.0f}/hr | ETA {((len(tasks)-len(results))/max(rate,1))*60:.0f}min")

    # 汇总
    elapsed_total = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"v0.1.4 DGIC 全量运行完成")
    print(f"{'='*60}")
    print(f"总计: {len(results)} 次运行")
    print(f"完成: {completed_count} ({completed_count/len(results)*100:.1f}%)")
    print(f"失败: {failed_count} ({failed_count/len(results)*100:.1f}%)")
    print(f"总耗时: {elapsed_total/60:.1f} 分钟")

    # 按病例汇总
    by_case = {}
    for r in results:
        cid = r["hadm_id"]
        if cid not in by_case:
            by_case[cid] = {"total": 0, "completed": 0, "turns": [], "tools": []}
        by_case[cid]["total"] += 1
        if r["completed"]:
            by_case[cid]["completed"] += 1
            by_case[cid]["turns"].append(r["turns"])
            by_case[cid]["tools"].append(r["tool_calls"])

    print(f"\n{'病例':<12} {'完成':<8} {'平均轮次':<10} {'平均工具':<10}")
    print("-"*45)
    for cid in sorted(by_case.keys()):
        d = by_case[cid]
        avg_t = sum(d["turns"])/len(d["turns"]) if d["turns"] else 0
        avg_tc = sum(d["tools"])/len(d["tools"]) if d["tools"] else 0
        print(f"{cid:<12} {d['completed']}/{d['total']:<6} {avg_t:<10.1f} {avg_tc:<10.1f}")

    # 保存汇总
    summary = {
        "version": "v0.1.4-dgic",
        "model": MEDICAL_MODEL,
        "timestamp": datetime.now().isoformat(),
        "total_runs": len(results),
        "completed": completed_count,
        "failed": failed_count,
        "completion_rate": completed_count/len(results)*100,
        "total_time_minutes": elapsed_total/60,
        "by_case": {cid: {
            "completed": d["completed"], "total": d["total"],
            "avg_turns": sum(d["turns"])/len(d["turns"]) if d["turns"] else 0,
            "avg_tools": sum(d["tools"])/len(d["tools"]) if d["tools"] else 0,
        } for cid, d in by_case.items()},
        "results": results,
    }
    summary_path = SAVE_DIR / f"batch_v014_all_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n汇总已保存: {summary_path}")

if __name__ == "__main__":
    main()
