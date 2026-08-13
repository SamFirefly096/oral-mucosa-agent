#!/usr/bin/env python3
"""Parallel batch batch_C: 24 runs (Chief_Realistic x all 24 cases)"""
import sys, os, time, json, traceback
from pathlib import Path

PROJECT_ROOT = Path('/opt/oral-mucosa-agent')
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))
os.environ['MIRA_ENABLE_THINKING'] = 'false'

from database import get_hpi_text, query_table
from agents_enhanced import ChiefMedAgent, RealisticPatientAgent, PatientContext
from conversation import run_conversation
from config import SAVE_DIR, MEDICAL_MODEL, PATIENT_MODEL

ALL_24 = [
    "OLP001","PV001","OC001","RAS001","HSV001","DLE001","LEUK001","EM001",
    "ANUG001","LR001","ATOLP001","BP001","ROM001","LEUK002","PV002","HZ001",
    "EM002","AOU001","MRAS001","OLL001","WSN001","CC001","PIM001","MRS001",
]

total = len(ALL_24)
ok = 0
fail = 0
t0_total = time.time()

label = 'Chief_Realistic'
print(f'\n{"="*40}\n{label}  ({total} cases)\n{"="*40}', flush=True)

for hadm_id in ALL_24:
    p = query_table('patients', hadm_id)
    cc = query_table('chief_complaints', hadm_id)
    if not p or not cc:
        print(f'  SKIP {hadm_id}: no data', flush=True)
        continue

    primary_complaint = cc.get('chief_complaint', '')
    ctx = PatientContext(
        hadm_id=hadm_id,
        patient_info_text=get_hpi_text(hadm_id),
        age=p.get('age'),
        gender=p.get('gender'),
    )

    try:
        med = ChiefMedAgent(model=MEDICAL_MODEL, thinking=False)
        pat = RealisticPatientAgent(model=PATIENT_MODEL)
        pat.init_with_patient(ctx)

        t0 = time.time()
        result = run_conversation(
            med_agent=med, patient_agent=pat, patient_context=ctx,
            primary_complaint=primary_complaint, verbose=False, max_turns=35,
        )
        elapsed = time.time() - t0

        ts = time.strftime('%Y%m%d_%H%M%S')
        fn = f'{hadm_id}_{label}_{ts}.json'
        output = {
            'hadm_id': hadm_id,
            'label': label,
            'conversation_log': result['conversation_log'],
            'statistics': result.get('statistics', {}),
            'completed': result.get('completed', False),
        }
        with open(SAVE_DIR / fn, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        s = result.get('statistics', {})
        ok += 1
        pct = ok / total * 100 if total > 0 else 0
        elapsed_total = time.time() - t0_total
        rate = ok / (elapsed_total / 3600) if elapsed_total > 0 else 0
        msg = (
            f'  [{ok}/{total} ({pct:.0f}%)] {hadm_id} {label} OK '
            f'{elapsed:.0f}s {s.get("total_turns",0)}t/{s.get("tool_calls",0)}tc '
            f'({rate:.0f}/hr)'
        )
        print(msg, flush=True)

    except Exception as ex:
        fail += 1
        traceback.print_exc()
        print(f'  [{ok}/{total}] {hadm_id} {label} FAIL: {ex}', flush=True)

elapsed_total = time.time() - t0_total
print(f'\n{"="*40}\nbatch_C DONE: {ok}/{total} ok, {fail} fail, {elapsed_total/60:.0f}min\n{"="*40}', flush=True)
