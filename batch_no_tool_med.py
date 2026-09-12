"""
零工具医生智能体 × 真实混乱型患者：24 例全量测试
- 医生智能体禁用全部检查类工具与知识检索（数据库、教科书），仅保留诊断提交
- 仅依赖模型自身知识与推理能力
- 模型 deepseek-v4-pro，引擎 conversation_v014，与历史实验同参数
用法: python3 batch_no_tool_med.py
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

from config import SAVE_DIR, RESULTS_DIR  # noqa: E402
from conversation_v014 import run_conversation, save_result  # noqa: E402
from agents_enhanced import ChiefMedAgent, RealisticPatientAgent  # noqa: E402
from batch_chief_real_v41 import load_patient, CASE_LIST  # noqa: E402

lock = threading.Lock()
LABEL_SUFFIX = "notool"


class NoToolChiefMedAgent(ChiefMedAgent):
    """禁用全部检查类工具与知识检索，仅保留 finalize_diagnosis"""

    def _build_tool_schemas(self):
        schemas = super()._build_tool_schemas()
        return [s for s in schemas if "finalize" in s["function"]["name"]]


def run_one(hadm_id, patient_ctx, complaint):
    label = f"{hadm_id}_Chief_Realistic_{LABEL_SUFFIX}"
    try:
        med = NoToolChiefMedAgent(model=MODEL, thinking=False)
        pat = RealisticPatientAgent(model=MODEL)
        pat.init_with_patient(patient_ctx)
        result = run_conversation(med_agent=med, patient_agent=pat,
                                  patient_context=patient_ctx,
                                  primary_complaint=complaint,
                                  max_turns=30, verbose=False)
        result["label"] = label
        result["timestamp"] = datetime.now().isoformat()
        result["agent_mode"] = "no_tool（禁用数据库与教科书检索）"
        save_result(result, hadm_id, label)
        stats = result["statistics"]
        diag = ""
        for e in reversed(result.get("conversation_log", [])):
            tc = e.get("tool_call", {})
            if tc.get("name") == "finalize_diagnosis":
                diag = tc.get("arguments", {}).get("primary_diagnosis", "")
                break
        return {"label": label, "hadm_id": hadm_id, "completed": result["completed"],
                "diagnosis": diag, "turns": stats["total_turns"],
                "tools": stats["tool_calls"], "time": stats["total_time_seconds"]}
    except Exception as e:
        return {"label": label, "hadm_id": hadm_id, "completed": False,
                "diagnosis": "", "turns": 0, "tools": 0, "time": 0,
                "error": str(e)[:200]}


def main():
    print(f"零工具医生智能体 × 真实混乱型患者 | 模型 {MODEL} | 24 例 | 并行 3", flush=True)
    print(f"开始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    tasks = []
    for cid in CASE_LIST:
        try:
            tasks.append((cid, *load_patient(cid)))
        except Exception as e:
            print(f"  [SKIP] {cid}: {e}", flush=True)
    results, t0 = [], time.time()
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(run_one, *t): t for t in tasks}
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            with lock:
                st = "OK" if r["completed"] else ("ERR" if r.get("error") else "FAIL")
                print(f"[{len(results)}/{len(tasks)}] {r['hadm_id']:<9} {st} "
                      f"t={r['turns']} tc={r['tools']} {r['time']:.0f}s :: "
                      f"{(r['diagnosis'] or '(无诊断)')[:46]}", flush=True)
    elapsed = time.time() - t0
    done = sum(1 for r in results if r["completed"])
    summary = {
        "experiment": "no_tool_agent（禁用数据库与教科书检索，仅模型自身能力）",
        "model": MODEL, "patient": "RealisticPatientAgent（真实混乱型）",
        "engine": "conversation_v014", "timestamp": datetime.now().isoformat(),
        "total": len(results), "completed": done,
        "completion_rate": done / max(len(results), 1) * 100,
        "avg_turns": sum(r["turns"] for r in results) / max(len(results), 1),
        "avg_time": sum(r["time"] for r in results) / max(len(results), 1),
        "elapsed_minutes": elapsed / 60, "results": results,
    }
    path = RESULTS_DIR / "batch_no_tool_summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{'='*64}")
    print(f"完成 {done}/{len(results)}（{done/max(len(results),1)*100:.1f}%）｜"
          f"均轮次 {summary['avg_turns']:.1f}｜均耗时 {summary['avg_time']:.0f}s｜"
          f"总耗时 {elapsed/60:.1f} 分钟")
    print(f"汇总: {path}")


if __name__ == "__main__":
    main()
