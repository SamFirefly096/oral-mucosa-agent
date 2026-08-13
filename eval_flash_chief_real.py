
# -*- coding: utf-8 -*-
import sys, os, json, glob
sys.path.insert(0, '/opt/oral-mucosa-agent')
from remote_eval import normalize_diagnosis, extract_diagnosis, DISEASE_CATEGORIES
from database import query_table

TARGET = ["OLP001","PV001","OC001","RAS001","HSV001","DLE001","LEUK001","EM001","ANUG001","LR001","ATOLP001","BP001","ROM001","LEUK002","PV002","HZ001","EM002","AOU001","MRAS001","OLL001","WSN001","CC001","PIM001","MRS001"]
OUT = '/opt/oral-mucosa-agent/outputs/logs/eval_flash_chief_real.txt'
lines = []

def p(s=''):
    lines.append(str(s))

files = sorted(glob.glob('/opt/oral-mucosa-agent/outputs/conversations/*flash*.json'))
best = {}
for fn in files:
    try:
        with open(fn, encoding='utf-8', errors='replace') as f:
            d = json.load(f)
    except Exception as e:
        continue
    hadm = d.get('hadm_id', '')
    label = d.get('label', '')
    if hadm not in TARGET:
        continue
    if not label.endswith('_Chief_Realistic_flash'):
        continue
    if hadm not in best:
        best[hadm] = (fn, d)
    else:
        old_fn, old_d = best[hadm]
        if d.get('completed') and not old_d.get('completed'):
            best[hadm] = (fn, d)
        elif d.get('completed') == old_d.get('completed') and fn > old_fn:
            best[hadm] = (fn, d)

def get_diag_text(d):
    # 1) any finalize_diagnosis tool_call in conversation_log (last non-empty wins)
    cl = d.get('conversation_log', [])
    found = ''
    for e in cl:
        tc = e.get('tool_call')
        if isinstance(tc, dict) and tc.get('name') == 'finalize_diagnosis':
            args = tc.get('arguments')
            if isinstance(args, dict):
                pd = str(args.get('primary_diagnosis', '')).strip()
                if pd:
                    found = pd
    if found:
        return found
    # 2) remote_eval style: terminated entries
    t = extract_diagnosis(d)
    if t:
        return t
    # 3) top-level tool_calls dict
    tc = d.get('tool_calls')
    if isinstance(tc, dict):
        fd = tc.get('finalize_diagnosis')
        if isinstance(fd, dict):
            args = fd.get('arguments', {})
            if isinstance(args, dict):
                return str(args.get('primary_diagnosis', ''))
    # 4) last content with 诊断
    for e in reversed(cl):
        content = str(e.get('content', ''))
        if '诊断' in content and len(content) > 20:
            return content[:300]
    return ''

total = 0
completed = 0
correct = 0
p('病例 | 真值(数据库) | 真值归类 | agent诊断(primary_diagnosis) | agent归类 | 匹配')
p('=' * 130)
for hadm in sorted(TARGET):
    total += 1
    if hadm not in best:
        p('%s | 无flash对话文件' % hadm)
        continue
    fn, d = best[hadm]
    if not d.get('completed'):
        p('%s | 未完成 (%s)' % (hadm, fn.split('/')[-1]))
        continue
    completed += 1
    diag_text = get_diag_text(d)
    agent_cat = normalize_diagnosis(diag_text)
    true_row = query_table('diagnoses', hadm)
    true_text = str(true_row.get('primary_diagnosis', '')) if true_row else ''
    true_cat = normalize_diagnosis(true_text)
    ok = bool(agent_cat and true_cat and agent_cat == true_cat)
    if ok:
        correct += 1
    match = '是' if ok else ('否' if agent_cat else 'N/A(agent未归类)')
    p('%s | %s | %s | %s | %s | %s' % (
        hadm,
        true_text.replace('\n', ' ')[:50],
        true_cat,
        diag_text.replace('\n', ' ')[:90],
        agent_cat,
        match))
p('=' * 130)
p('完成率: %d/%d (%.1f%%)' % (completed, total, completed * 100.0 / total))
p('准确率: %d/%d (%.1f%%)' % (correct, completed, correct * 100.0 / completed if completed else 0))
with open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print('WROTE ' + OUT)
