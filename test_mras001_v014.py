"""v0.1.4 DGIC — MRAS001专项测试（修复版：无数据泄露）"""
import sys, os, json, time
from datetime import datetime

PROJECT_ROOT = "/opt/oral-mucosa-agent"
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from config import SAVE_DIR, MEDICAL_MODEL, PATIENT_MODEL
from conversation_v014 import run_conversation, save_result
from agents_enhanced import (
    LearningMedAgent, TextbookMedAgent, ChiefMedAgent,
    OriginalPatientAgent, RealisticPatientAgent, PatientContext,
)
from database import query_table


def load_patient(hadm_id: str):
    p = query_table("patients", hadm_id)
    if not p:
        raise ValueError(f"病例 {hadm_id} 不存在")
    cc = query_table("chief_complaints", hadm_id)
    from database import get_hpi_text
    hpi = get_hpi_text(hadm_id) or ""
    info_parts = [hpi]
    # v0.1.4-fix: 不包含diagnoses和treatments，防止数据泄露
    safe_tables = ['oral_examinations', 'lab_results', 'microbiology_results', 'pathology_results']
    for table in safe_tables:
        row = query_table(table, hadm_id)
        if row:
            fields = {k: v for k, v in row.items()
                     if k not in ('id', 'hadm_id') and v is not None and v != ''}
            if fields:
                info_parts.append(f"{table}: {json.dumps(fields, ensure_ascii=False)}")
    patient_info = "\\n".join(info_parts)
    complaint = cc.get('chief_complaint', '') if cc else ''
    if not complaint and hpi:
        complaint = hpi.split('。')[0] if '。' in hpi else hpi[:100]
    return PatientContext(hadm_id=hadm_id, patient_info_text=patient_info,
                          age=p.get('age'), gender=p.get('gender', '')), complaint


def run_test(hadm_id: str, combinations=None):
    if combinations is None:
        combinations = [
            ("Learn", "Original"), ("Learn", "Realistic"),
            ("Textbook", "Original"), ("Textbook", "Realistic"),
            ("Chief", "Original"), ("Chief", "Realistic"),
        ]
    patient_ctx, complaint = load_patient(hadm_id)
    print(f"\\n{'#'*60}")
    print(f"# v0.1.4 DGIC 测试 — {hadm_id}")
    print(f"# 模型: MED={MEDICAL_MODEL}, PAT={PATIENT_MODEL}")
    print(f"# 组合数: {len(combinations)}")
    print(f"# 开始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*60}")
    results = []
    for med_type, pat_type in combinations:
        label = f"{med_type}_{pat_type}"
        print(f"\\n{'─'*60}\\n  [{label}] 开始...\\n{'─'*60}")
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
                max_turns=30, verbose=True)
            result["label"] = label
            result["model"] = MEDICAL_MODEL
            result["timestamp"] = datetime.now().isoformat()
            filepath = save_result(result, hadm_id, label)
            results.append({
                "label": label, "completed": result["completed"],
                "turns": result["statistics"]["total_turns"],
                "tool_calls": result["statistics"]["tool_calls"],
                "time_seconds": result["statistics"]["total_time_seconds"],
                "file": str(filepath), "error": None,
            })
            print(f"  [{label}] 完成: completed={result['completed']}, turns={result['statistics']['total_turns']}, tools={result['statistics']['tool_calls']}, time={result['statistics']['total_time_seconds']}s")
        except Exception as e:
            import traceback
            traceback.print_exc()
            results.append({"label": label, "completed": False, "turns": 0, "tool_calls": 0, "time_seconds": 0, "file": None, "error": str(e)})
    print(f"\\n{'='*60}\\n  测试汇总: {hadm_id}\\n{'='*60}")
    completed = sum(1 for r in results if r["completed"])
    for r in results:
        s = "OK" if r["completed"] else "FAIL"
        print(f"{r['label']:<25} {s} turns={r['turns']} tools={r['tool_calls']} time={r['time_seconds']}s")
    print(f"\\n  完成率: {completed}/{len(results)} ({completed/len(results)*100:.1f}%)")
    summary_path = SAVE_DIR / f"{hadm_id}_v014_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({"hadm_id": hadm_id, "version": "v0.1.4-dgic", "model": MEDICAL_MODEL,
                   "timestamp": datetime.now().isoformat(), "results": results},
                  f, ensure_ascii=False, indent=2)
    return results


if __name__ == "__main__":
    hadm_id = sys.argv[1] if len(sys.argv) > 1 else "MRAS001"
    if len(sys.argv) >= 3:
        med_filter = sys.argv[2]
        pat_filter = sys.argv[3] if len(sys.argv) >= 4 else None
        combos = [(m, p) for m in ["Learn","Textbook","Chief"]
                  for p in ["Original","Realistic"]
                  if m == med_filter and (pat_filter is None or p == pat_filter)]
        run_test(hadm_id, combos)
    else:
        run_test(hadm_id)
