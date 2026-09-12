"""
基础能力对照实验：医生智能体仅保留检查工具，禁用教科书知识检索，
使用无自反思、无鉴别诊断驱动提示的纯净对话引擎，对 24 例真实混乱型患者测试。

- 医生工具：口腔检查 / 中医四诊 / 化验 / 微生物 / 病理 / 处方 / 诊断提交
- 禁用工具：search_clinical_knowledge（教科书与病例知识库检索）
- 检查工具只返回客观所见，不含诊断提示
- 对话引擎：conversation_plain（无自反思、无 DGIC）
用法: python3 batch_plain_med.py
"""
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

MODEL = os.environ.get("PLAIN_MODEL", "deepseek-v4-pro")
os.environ["MIRA_MEDICAL_MODEL"] = MODEL
os.environ["MIRA_PATIENT_MODEL"] = MODEL

PROJECT_ROOT = "/opt/oral-mucosa-agent"
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from config import RESULTS_DIR  # noqa: E402
from conversation_plain import run_conversation, save_result  # noqa: E402
from agents_enhanced import ChiefMedAgent, RealisticPatientAgent  # noqa: E402
from batch_chief_real_v41 import load_patient, CASE_LIST  # noqa: E402

lock = threading.Lock()
LABEL_SUFFIX = os.environ.get("PLAIN_LABEL", "plain")
BANNED = {"search_clinical_knowledge"}


class PlainChiefMedAgent(ChiefMedAgent):
    """禁用教科书/知识库检索，保留检查与诊断工具"""

    def _build_tool_schemas(self):
        schemas = super()._build_tool_schemas()
        return [s for s in schemas if s["function"]["name"] not in BANNED]


def run_one(hadm_id, patient_ctx, complaint):
    label = f"{hadm_id}_Chief_Realistic_{LABEL_SUFFIX}"
    try:
        med = PlainChiefMedAgent(model=MODEL, thinking=False)
        pat = RealisticPatientAgent(model=MODEL)
        pat.init_with_patient(patient_ctx)
        result = run_conversation(med_agent=med, patient_agent=pat,
                                  patient_context=patient_ctx,
                                  primary_complaint=complaint,
                                  max_turns=30, verbose=False)
        result["label"] = label
        result["timestamp"] = datetime.now().isoformat()
        result["agent_mode"] = "plain（无教科书检索、无自反思、无 DGIC）"
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
                "error": f"{type(e).__name__}: {str(e)[:180]}"}


def main():
    print(f"基础能力对照实验 | 模型 {MODEL} | 24 例 | 并行 3", flush=True)
    print(f"医生：保留检查工具，禁用教科书检索；引擎：无自反思、无 DGIC", flush=True)
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
        "experiment": "plain_agent（保留检查工具，禁用教科书检索，无自反思与 DGIC）",
        "model": MODEL, "patient": "RealisticPatientAgent（真实混乱型）",
        "engine": "conversation_plain", "timestamp": datetime.now().isoformat(),
        "total": len(results), "completed": done,
        "completion_rate": done / max(len(results), 1) * 100,
        "avg_turns": sum(r["turns"] for r in results) / max(len(results), 1),
        "avg_tools": sum(r["tools"] for r in results) / max(len(results), 1),
        "avg_time": sum(r["time"] for r in results) / max(len(results), 1),
        "elapsed_minutes": elapsed / 60, "results": results,
    }
    path = RESULTS_DIR / f"batch_plain_{LABEL_SUFFIX}_summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{'='*64}")
    print(f"完成 {done}/{len(results)}（{done/max(len(results),1)*100:.1f}%）｜"
          f"均轮次 {summary['avg_turns']:.1f}｜均工具 {summary['avg_tools']:.1f}｜"
          f"均耗时 {summary['avg_time']:.0f}s｜总耗时 {elapsed/60:.1f} 分钟")
    print(f"汇总: {path}")


if __name__ == "__main__":
    main()
