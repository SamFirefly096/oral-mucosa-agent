import json, re, glob
from database import query_table

files = sorted(glob.glob('outputs/conversations/*.json'))
hadm_ids = set()
for f in files:
    m = re.match(r'([A-Z]+\d+)_', f.split('\\')[-1] if '\\' in f else f.split('/')[-1])
    if m: hadm_ids.add(m.group(1))

print('Evaluating %d cases:' % len(hadm_ids))
print('%-12s %-3s %-3s %-3s %s' % ('Case', 'W-D', 'TCM', 'Adm', 'Agent Diagnosis (core)'))
print('-' * 90)

correct_w = 0
correct_tcm = 0
correct_adm = 0
total = 0

for hadm_id in sorted(hadm_ids):
    matching = [f for f in files if hadm_id in f]
    latest = sorted(matching)[-1]
    with open(latest, 'r', encoding='utf-8') as fh:
        data = json.load(fh)

    agent_diag = ''
    tcm_syndrome = ''
    agent_adm = ''
    for entry in data.get('conversation_log', []):
        tc = entry.get('tool_call', {})
        if tc.get('name') == 'finalize_diagnosis':
            args = tc.get('arguments', {})
            agent_diag = args.get('primary_diagnosis', '')
            tcm_syndrome = args.get('tcm_syndrome', '')
            agent_adm = args.get('admission_needed', '')

    true = query_table('diagnoses', hadm_id)
    true_diag = true.get('primary_diagnosis', '') if true else ''
    true_tcm = query_table('tcm_diagnoses', hadm_id)
    true_syn = true_tcm.get('syndrome_differentiation', '') if true_tcm else ''
    true_treat = query_table('treatments', hadm_id)
    true_adm = true_treat.get('admission_needed', 'no') if true_treat else 'no'

    # Core word matching
    def core_words(s):
        s = re.sub(r'[\uff08\uff09()\uff0c,\-a-zA-Z\s/]+', '', s.lower())
        return set(s[i:i+2] for i in range(len(s)-1))

    diag_match = False
    agent_core = core_words(agent_diag)
    true_core = core_words(true_diag)
    if true_core and agent_core:
        diag_match = len(agent_core & true_core) >= len(true_core) * 0.4

    tcm_match = False
    if tcm_syndrome and true_syn:
        tcm_match = any(kw in tcm_syndrome for kw in true_syn.replace('\u8bc1','').replace('\u517c','').replace('\u6709','').split('\u3001') if len(kw) > 1)

    adm_match = agent_adm == true_adm

    total += 1
    if diag_match: correct_w += 1
    if tcm_match: correct_tcm += 1
    if adm_match: correct_adm += 1

    w_icon = 'OK' if diag_match else '??'
    t_icon = 'OK' if tcm_match else '??'
    a_icon = 'OK' if adm_match else 'XX'

    short_diag = agent_diag[:60] + ('...' if len(agent_diag)>60 else '')
    print('%-12s %-3s %-3s %-3s %s' % (hadm_id, w_icon, t_icon, a_icon, short_diag))

print('')
print('=' * 90)
print('Western Dx correct: %d/%d (%.1f%%)' % (correct_w, total, correct_w/total*100 if total else 0))
print('TCM Syndrome correct: %d/%d (%.1f%%)' % (correct_tcm, total, correct_tcm/total*100 if total else 0))
print('Admission correct: %d/%d (%.1f%%)' % (correct_adm, total, correct_adm/total*100 if total else 0))
