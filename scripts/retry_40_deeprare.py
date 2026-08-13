#!/usr/bin/env python3
"""Re-run 40 incomplete cases from v0.1.2 with DeepRare-mode reflection"""
import sys, os, time, json
from pathlib import Path

PROJECT_ROOT = Path('/opt/oral-mucosa-agent')
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))
os.environ['MIRA_ENABLE_THINKING'] = 'false'

from database import get_hpi_text, query_table
from agents_enhanced import LearningMedAgent, TextbookMedAgent, ChiefMedAgent, OriginalPatientAgent, RealisticPatientAgent, PatientContext
from conversation import run_conversation
from config import SAVE_DIR, MEDICAL_MODEL, PATIENT_MODEL

CONFIG_CLASSES = {
    'Learn': LearningMedAgent,
    'Textbook': TextbookMedAgent,
    'Chief': ChiefMedAgent,
    'Original': OriginalPatientAgent,
    'Realistic': RealisticPatientAgent,
}

# 40个未完成病例
RETRY = [
    # (doc_name, pat_name, [hadm_ids])
    ("Learn", "Original", ["DLE001","ROM001","AOU001","MRAS001","OLL001"]),
    ("Learn", "Realistic", ["OLP001","AOU001","MRAS001","PIM001","MRS001"]),
    ("Textbook", "Original", ["ROM001","AOU001","MRAS001","WSN001","CC001","PIM001","MRS001"]),
    ("Textbook", "Realistic", ["LR001","ATOLP001","ROM001","LEUK002","AOU001","MRAS001","OLL001","CC001"]),
    ("Chief", "Original", ["ATOLP001","MRAS001","OLL001","PIM001"]),
    ("Chief", "Realistic", ["RAS001","DLE001","EM001","LR001","ROM001","LEUK002","HZ001","AOU001","MRAS001","PIM001","MRS001"]),
]

# 删除这些病例的旧文件（避免跳过逻辑）
for doc_name, pat_name, cases in RETRY:
    label = f"{doc_name}_{pat_name}"
    for hadm_id in cases:
        for old_fn in SAVE_DIR.glob(f"{hadm_id}_{label}_*.json"):
            old_fn.unlink()
            print(f"已删除旧文件: {old_fn.name}")

total = sum(len(cases) for _, _, cases in RETRY)
ok = 0
fail = 0
t0_total = time.time()

for doc_name, pat_name, cases in RETRY:
    DocClass = CONFIG_CLASSES[doc_name]
    PatClass = CONFIG_CLASSES[pat_name]
    label = f"{doc_name}_{pat_name}"
    print(f'\n{"="*50}\n{label} ({len(cases)} cases)\n{"="*50}', flush=True)

    for hadm_id in cases:
        p = query_table('patients', hadm_id)
        cc = query_table('chief_complaints', hadm_id)
        if not p or not cc:
            print(f'  SKIP {hadm_id}', flush=True)
            continue

        ctx = PatientContext(hadm_id=hadm_id, patient_info_text=get_hpi_text(hadm_id), age=p.get('age'), gender=p.get('gender'))

        try:
            med = DocClass(model=MEDICAL_MODEL, thinking=False)
            pat = PatClass(model=PATIENT_MODEL)
            pat.init_with_patient(ctx)

            t0 = time.time()
            result = run_conversation(med_agent=med, patient_agent=pat, patient_context=ctx, primary_complaint='', verbose=False, max_turns=40)
            elapsed = time.time() - t0

            ts = time.strftime('%Y%m%d_%H%M%S')
            fn = f'{hadm_id}_{label}_{ts}.json'
            output = {'hadm_id': hadm_id, 'label': label, 'conversation_log': result['conversation_log'], 'statistics': result['statistics'], 'completed': result['completed']}
            with open(SAVE_DIR / fn, 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2)

            s = result['statistics']
            ok += 1
            pct = ok / total * 100
            elapsed_total = time.time() - t0_total
            msg = f'  [{ok}/{total} ({pct:.0f}%)] {hadm_id} {label} OK {elapsed:.0f}s {s["total_turns"]}t/{s["tool_calls"]}tc completed={result["completed"]}'
            print(msg, flush=True)
        except Exception as ex:
            fail += 1
            print(f'  [{ok}/{total}] {hadm_id} {label} FAIL: {ex}', flush=True)

elapsed_total = time.time() - t0_total
summary = f'\n{"="*50}\nRETRY DONE: {ok}/{total} ok, {fail} fail, {elapsed_total/60:.0f}min\n{"="*50}'
print(summary, flush=True)
