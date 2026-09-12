"""
MRAS001 数据库描述修正后重跑验证：6 个「医生 × 患者」组合 × 3 次重复
- 数据库修正：病损描述由「深大糜烂面」改为「深大溃疡（边缘隆起，基底覆黄白假膜）」
- 模型固定为 deepseek-v4-pro（与历史正式实验一致），引擎 conversation_v014
- 结果写入 outputs/conversations/*_mrasfix_*.json，汇总 outputs/results/mras001_after_fix.json
用法: python3 rerun_mras001_after_fix.py
"""
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

MODEL = "deepseek-v4-pro"
os.environ["MIRA_MEDICAL_MODEL"] = MODEL
os.environ["MIRA_PATIENT_MODEL"] = MODEL

PROJECT_ROOT = "/opt/oral-mucosa-agent"
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from config import RESULTS_DIR  # noqa: E402
from conversation_v014 import run_conversation, save_result  # noqa: E402
from agents_enhanced import (  # noqa: E402
    ChiefMedAgent, LearningMedAgent, TextbookMedAgent,
    OriginalPatientAgent, RealisticPatientAgent,
)
from batch_chief_real_v41 import load_patient  # noqa: E402

CASE = "MRAS001"
REPEATS = 1
# Learn 组已完成（mrasfix1-3），本轮只补 Textbook / Chief 各 2 组
COMBOS = [
    ("Textbook", TextbookMedAgent, "Original", OriginalPatientAgent),
    ("Textbook", TextbookMedAgent, "Realistic", RealisticPatientAgent),
    ("Chief", ChiefMedAgent, "Original", OriginalPatientAgent),
    ("Chief", ChiefMedAgent, "Realistic", RealisticPatientAgent),
]
lock = threading.Lock()


def is_correct(diag: str) -> bool:
    d = (diag or "").lower()
    return ("阿弗他" in d) or ("aphthous" in d) or ("maras" in d) or ("marau" in d)


def run_one(doc_name, DocCls, pat_name, PatCls, rep):
    label = f"{CASE}_{doc_name}_{pat_name}_mrasfix{rep}"
    try:
        ctx, complaint = load_patient(CASE)
        med = DocCls(model=MODEL, thinking=False)
        pat = PatCls(model=MODEL)
        pat.init_with_patient(ctx)
        result = run_conversation(med_agent=med, patient_agent=pat, patient_context=ctx,
                                  primary_complaint=complaint, max_turns=30, verbose=False)
        result["label"] = label
        result["timestamp"] = datetime.now().isoformat()
        save_result(result, CASE, label)
        diag = ""
        for e in reversed(result.get("conversation_log", [])):
            tc = e.get("tool_call", {})
            if tc.get("name") == "finalize_diagnosis":
                diag = tc.get("arguments", {}).get("primary_diagnosis", "")
                break
        return {"label": label, "doc": doc_name, "pat": pat_name, "rep": rep,
                "completed": result.get("completed", False), "diagnosis": diag,
                "correct": is_correct(diag), "turns": result["statistics"]["total_turns"],
                "tools": result["statistics"]["tool_calls"]}
    except Exception as e:
        return {"label": label, "doc": doc_name, "pat": pat_name, "rep": rep,
                "completed": False, "diagnosis": "", "correct": False,
                "turns": 0, "tools": 0, "error": str(e)[:200]}


def main():
    print(f"MRAS001 重跑验证 | 模型 {MODEL} | 组合 {len(COMBOS)} × {REPEATS} 次 = {len(COMBOS)*REPEATS} 次", flush=True)
    print(f"开始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    tasks = [(d, D, p, P, r) for d, D, p, P in COMBOS for r in range(1, REPEATS + 1)]
    results, t0 = [], time.time()
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(run_one, *t): t for t in tasks}
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            with lock:
                status = "OK" if r["correct"] else ("ERR" if r.get("error") else "MISS")
                print(f"[{len(results)}/{len(tasks)}] {r['doc']:<9}×{r['pat']:<9} #{r['rep']} {status} "
                      f"t={r['turns']} :: {(r['diagnosis'] or '(无诊断)')[:52]}", flush=True)
    elapsed = time.time() - t0
    # 汇总
    summary = {}
    for d, D, p, P in COMBOS:
        rows = [r for r in results if r["doc"] == d and r["pat"] == p]
        summary[f"{d} × {p}"] = {
            "n": len(rows),
            "correct": sum(1 for r in rows if r["correct"]),
            "diagnoses": [r["diagnosis"][:60] for r in rows],
        }
    out = {"case": CASE, "model": MODEL, "timestamp": datetime.now().isoformat(),
           "repeats": REPEATS, "elapsed_seconds": round(elapsed, 1),
           "summary": summary, "results": results}
    path = RESULTS_DIR / "mras001_after_fix.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{'='*66}")
    print("组合汇总（正确 / 总数）:")
    for k, v in summary.items():
        print(f"  {k:<22} {v['correct']}/{v['n']}   诊断: {' / '.join(x or '(无)' for x in v['diagnoses'])}")
    tot_c = sum(v["correct"] for v in summary.values())
    tot_n = sum(v["n"] for v in summary.values())
    print(f"\n合计正确率: {tot_c}/{tot_n} = {tot_c/tot_n*100:.1f}%")
    print(f"耗时: {elapsed/60:.1f} 分钟 | 汇总: {path}")


if __name__ == "__main__":
    main()
