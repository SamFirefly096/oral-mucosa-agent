"""MRAS001 用新数据库重跑：v4.1 Flash + DGIC 引擎 + 全工具（含教科书检索），3 次"""
import json, os, sys, time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

MODEL = "deepseek-v4.1-flash-expires-on-0910"
os.environ["MIRA_MEDICAL_MODEL"] = MODEL
os.environ["MIRA_PATIENT_MODEL"] = MODEL
sys.path.insert(0, "/opt/oral-mucosa-agent"); os.chdir("/opt/oral-mucosa-agent")

from config import RESULTS_DIR
from conversation_v014 import run_conversation, save_result
import agents_enhanced
from agents_enhanced import ChiefMedAgent, RealisticPatientAgent

EFFORT = os.environ.get("EFFORT", "")
if EFFORT:
    _orig_tep = agents_enhanced.thinking_extra_param
    def _patched_tep(enabled):
        d = dict(_orig_tep(enabled))
        if enabled:
            d["reasoning_effort"] = EFFORT
        return d
    agents_enhanced.thinking_extra_param = _patched_tep
    print(f"[patch] reasoning_effort = {EFFORT}", flush=True)
from batch_chief_real_v41 import load_patient

REPEATS = 10
WORKERS = int(os.environ.get("WORKERS", "5"))
LABEL = os.environ.get("LABEL", "v41new")
THINKING = os.environ.get("THINKING", "0") == "1"
EFFORT_LABEL = os.environ.get("EFFORT", "default")


def run_one(rep):
    label = f"MRAS001_Chief_Realistic_{LABEL}{rep}"
    try:
        ctx, complaint = load_patient("MRAS001")
        med = ChiefMedAgent(model=MODEL, thinking=THINKING)
        pat = RealisticPatientAgent(model=MODEL)
        pat.init_with_patient(ctx)
        r = run_conversation(med_agent=med, patient_agent=pat, patient_context=ctx,
                             primary_complaint=complaint, max_turns=30, verbose=False)
        r["label"] = label
        r["timestamp"] = datetime.now().isoformat()
        r["agent_mode"] = "v4.1 Flash + DGIC + 全工具（新数据库）"
        save_result(r, "MRAS001", label)
        diag = ""
        for e in reversed(r.get("conversation_log", [])):
            tc = e.get("tool_call", {})
            if tc.get("name") == "finalize_diagnosis":
                diag = tc.get("arguments", {}).get("primary_diagnosis", ""); break
        return {"rep": rep, "completed": r["completed"], "diagnosis": diag,
                "turns": r["statistics"]["total_turns"], "tools": r["statistics"]["tool_calls"],
                "time": r["statistics"]["total_time_seconds"]}
    except Exception as e:
        return {"rep": rep, "completed": False, "diagnosis": "", "turns": 0, "tools": 0,
                "time": 0, "error": f"{type(e).__name__}: {str(e)[:150]}"}


def main():
    print(f"MRAS001 新数据库重跑 | {MODEL} | DGIC + 全工具 | {REPEATS} 次 | 并行 {WORKERS} | thinking={THINKING}", flush=True)
    t0 = time.time()
    rows = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for fut in as_completed([ex.submit(run_one, i) for i in range(1, REPEATS + 1)]):
            r = fut.result(); rows.append(r)
            ok = "正确" if ("阿弗他" in r["diagnosis"] or "MaRAS" in r["diagnosis"]) else "未通过"
            print(f"  #{r['rep']} {ok} t={r['turns']} tc={r['tools']} {r['time']:.0f}s :: "
                  f"{r['diagnosis'][:56] or '(无诊断)'}", flush=True)
    ok = sum(1 for r in rows if "阿弗他" in r["diagnosis"] or "MaRAS" in r["diagnosis"])
    out = {"case": "MRAS001", "model": MODEL, "engine": "conversation_v014(DGIC)",
           "tools": "全部（含教科书检索）", "db": "新数据库（病损描述=深大溃疡）", "thinking": THINKING, "reasoning_effort": EFFORT_LABEL,
           "repeats": REPEATS, "correct": ok, "results": sorted(rows, key=lambda x: x["rep"]),
           "elapsed": round(time.time() - t0, 1)}
    p = RESULTS_DIR / f"mras001_{LABEL}_summary.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n正确 {ok}/{REPEATS} | 耗时 {out['elapsed']/60:.1f} 分钟 | 汇总: {p}")


if __name__ == "__main__":
    main()
