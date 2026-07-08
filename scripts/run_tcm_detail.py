import json, re, glob
from database import query_table

files = sorted(glob.glob('outputs/conversations/*.json'))
hadm_ids = set()
for f in files:
    m = re.match(r'([A-Z]+\d+)_', f.split('\\')[-1] if '\\' in f else f.split('/')[-1])
    if m: hadm_ids.add(m.group(1))

print('=== TCM Diagnosis Detail ===')
print('')

for hadm_id in sorted(hadm_ids):
    matching = [f for f in files if hadm_id in f]
    latest = sorted(matching)[-1]
    with open(latest, 'r', encoding='utf-8') as fh:
        data = json.load(fh)

    tcm_syndrome = ''
    for entry in data.get('conversation_log', []):
        tc = entry.get('tool_call', {})
        if tc.get('name') == 'finalize_diagnosis':
            args = tc.get('arguments', {})
            tcm_syndrome = args.get('tcm_syndrome', '')

    true_tcm = query_table('tcm_diagnoses', hadm_id)
    true_syn = true_tcm.get('syndrome_differentiation', '') if true_tcm else ''

    # Matching
    if tcm_syndrome and true_syn:
        keywords = [kw for kw in true_syn.replace('\u8bc1','').replace('\u517c','').replace('\u6709','').split('\u3001') if len(kw) > 1]
        match_kw = [kw for kw in keywords if kw in tcm_syndrome]
        tcm_match = len(match_kw) > 0
    else:
        tcm_match = False
        keywords = []
        match_kw = []

    status = 'MATCH' if tcm_match else 'MISMATCH'
    print('='*80)
    print('[%s] %s' % (status, hadm_id))
    print('  True TCM:     %s' % true_syn)
    print('  Agent TCM:    %s' % tcm_syndrome)
    print('  Keywords:     %s' % json.dumps(keywords, ensure_ascii=False))
    print('  Matched:      %s' % json.dumps(match_kw, ensure_ascii=False))
    print('')

print('Done.')
