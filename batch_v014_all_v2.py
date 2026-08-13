"""
v0.1.4 DGIC 全量批量运行 v2（修复版）
24病例 x 6组合 = 144次实验，3路并行，跳过已完成
"""
import sys, os, json, time, traceback
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
from database import query_table, get_hpi_text

write_lock = threading.Lock()

# 24例标准病例列表
CASE_LIST = [
    "OLP001", "PV001", "OC001", "RAS001", "HSV001", "DLE001",
    "LEUK001", "EM001", "ANUG001", "LR001", "ATOLP001", "BP001",
    "ROM001", "LEUK002", "PV002", "HZ001", "EM002", "AOU001",
    "MRAS001", "OLL001", "WSN001", "CC001", "PIM001", "MRS001",
]

# 获取已完成的实验（用于跳过）
def get_completed_set():
    import glob as g
    completed = set()
    for f in g.glob(str(SAVE_DIR / "*_v014_*")):
        try:
            data = json.load(open(f))
            if data.get("completed"):
                completed.add(data.get("label", ""))
        except:
            pass
    return completed


def load_patient(hadm_id: str):
    p = query_table("patients", hadm_id)
    if not p:
        raise ValueError(f"Case {hadm_id} not found")
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
        return {"label": label, "hadm_id": hadm_id, "completed": result["completed"],
                "turns": stats["total_turns"], "tool_calls": stats["tool_calls"],
                "time_seconds": stats["total_time_seconds"], "file": str(filepath)}
    except Exception as e:
        return {"label": label, "hadm_id": hadm_id, "completed": False,
                "turns": 0, "tool_calls": 0, "time_seconds": 0,
                "file": None, "error": str(e)[:200]}


def main():
    skipped = get_completed_set()
    combos = [
        ("Learn", "Original"), ("Learn", "Realistic"),
        ("Textbook", "Original"), ("Textbook", "Realistic"),
        ("Chief", "Original"), ("Chief", "Realistic"),
    ]

    # 预加载患者
    patient_cache = {}
    for cid in CASE_LIST:
        try:
            patient_cache[cid] = load_patient(cid)
        except Exception as e:
            print(f"  [SKIP] {cid}: cannot load ({e})")

    # 构建任务列表（跳过已完成）
    tasks = []
    skip_count = 0
    for cid in CASE_LIST:
        if cid not in patient_cache:
            continue
        ctx, complaint = patient_cache[cid]
        for med_type, pat_type in combos:
            label = f"{cid}_{med_type}_{pat_type}"
            if label in skipped:
                skip_count += 1
                continue
            tasks.append((cid, med_type, pat_type, ctx, complaint))

    total = len(CASE_LIST) * len(combos)
    print(f"v0.1.4 DGIC 全量批量 v2")
    print(f"病例: {len(CASE_LIST)}, 组合: {len(combos)}, 总计: {total}")
    print(f"已跳过: {skip_count}, 待运行: {len(tasks)}")
    print(f"模型: MED={MEDICAL_MODEL}, PAT={PATIENT_MODEL}")
    print(f"并行: 3, max_turns: 30")
    print(f"开始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    if not tasks:
        print("所有实验已完成，无需运行！")
        return

    results = []
    completed_count = 0
    failed_count = 0
    t_start = time.time()

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(run_one, *t): t for t in tasks}
        for future in as_completed(futures):
            try:
                r = future.result()
            except Exception as e:
                t = futures[future]
                r = {"label": f"{t[0]}_{t[1]}_{t[2]}", "hadm_id": t[0],
                     "completed": False, "turns": 0, "tool_calls": 0,
                     "time_seconds": 0, "error": f"Future crashed: {e}"}
            results.append(r)
            if r["completed"]:
                completed_count += 1
            else:
                failed_count += 1
            elapsed = time.time() - t_start
            rate = len(results) / (elapsed / 3600) if elapsed > 0 else 0
            eta_min = (len(tasks) - len(results)) / max(rate, 1) * 60
            with write_lock:
                status = "OK" if r["completed"] else ("ERR" if r.get("error") else "FAIL")
                print(f"[{len(results)}/{len(tasks)}] {r['label']:<40} {status} t={r['turns']} tc={r['tool_calls']} {r['time_seconds']:.0f}s | {rate:.0f}/h ETA {eta_min:.0f}m")

    elapsed_total = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"v0.1.4 DGIC 全量完成")
    print(f"总计: {len(results)} 运行, 完成: {completed_count} ({completed_count/len(results)*100:.1f}%), 失败: {failed_count}")
    print(f"总耗时: {elapsed_total/60:.1f} 分钟")

    # 保存汇总
    summary = {
        "version": "v0.1.4-dgic",
        "model": MEDICAL_MODEL,
        "timestamp": datetime.now().isoformat(),
        "total_runs": len(results),
        "completed": completed_count,
        "failed": failed_count,
        "completion_rate": completed_count/len(results)*100 if results else 0,
        "total_time_minutes": elapsed_total/60,
        "results": results,
    }
    summary_path = SAVE_DIR / f"batch_v014_v2_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"汇总: {summary_path}")

if __name__ == "__main__":
    main()
