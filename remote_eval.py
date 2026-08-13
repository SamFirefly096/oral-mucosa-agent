import os, json, re
from collections import defaultdict
from database import query_table
from config import SAVE_DIR

DISEASE_CATEGORIES = {
    'oral_lichen_planus': {'name': '口腔扁平苔藓', 'keywords': ['扁平苔藓', 'OLP'], 'exclude': ['苔藓样']},
    'pemphigus_vulgaris': {'name': '寻常型天疱疮', 'keywords': ['天疱疮']},
    'oral_candidiasis': {'name': '口腔念珠菌病', 'keywords': ['念珠菌', '鹅口疮', 'candidiasis']},
    'recurrent_aphthous': {'name': '复发性阿弗他口炎', 'keywords': ['复发性阿弗他', 'RAU', '阿弗他溃疡', '阿弗他口炎']},
    'herpes_simplex': {'name': '口腔单纯疱疹', 'keywords': ['单纯疱疹', '疱疹性龈口炎', '疱疹性口炎']},
    'erythema_multiforme': {'name': '多形红斑', 'keywords': ['多形红斑', '多形性红斑']},
    'leukoplakia': {'name': '口腔白斑', 'keywords': ['白斑'], 'exclude': ['白色海绵']},
    'discoid_lupus': {'name': '盘状红斑狼疮', 'keywords': ['盘状红斑', '红斑狼疮', 'DLE']},
    'anug': {'name': '急性坏死性溃疡性龈炎', 'keywords': ['坏死性溃疡性龈炎', 'ANUG']},
    'lichenoid_reaction': {'name': '苔藓样反应', 'keywords': ['苔藓样反应', '苔藓样变']},
    'bullous_pemphigoid': {'name': '大疱性类天疱疮', 'keywords': ['类天疱疮']},
    'radiation_induced_oral_mucositis': {'name': '放射性口腔黏膜炎', 'keywords': ['放射性口腔黏膜炎']},
    'herpes_zoster': {'name': '带状疱疹', 'keywords': ['带状疱疹', 'herpes zoster']},
    'allergic_oral_ulceration': {'name': '过敏性口炎', 'keywords': ['过敏性口炎', '过敏', 'allergic stomatitis']},
    'major_recurrent_aphthous': {'name': '重型复发性阿弗他溃疡', 'keywords': ['重型.*阿弗他', '重型复发性口腔溃疡']},
    'oral_lichenoid_lesion': {'name': '口腔苔藓样病变', 'keywords': ['苔藓样病损', '苔藓样病变', 'lichenoid lesion']},
    'white_sponge_nevus': {'name': '白色海绵状斑痣', 'keywords': ['白色海绵']},
    'chronic_cheilitis': {'name': '慢性唇炎', 'keywords': ['慢性唇炎', '唇炎']},
    'peri_implant_mucositis': {'name': '种植体周围黏膜炎', 'keywords': ['种植体周围', 'peri-implant', '种植体周围炎']},
    'melkersson_rosenthal_syndrome': {'name': '梅罗综合征', 'keywords': ['梅罗', 'Melkersson', 'MRS']},
}

def normalize_diagnosis(diag_text):
    if not diag_text: return None
    diag_lower = diag_text.lower()
    best_match, best_priority = None, 999
    for cat_key, cat_info in DISEASE_CATEGORIES.items():
        for kw in cat_info['keywords']:
            if kw.lower() in diag_lower:
                excluded = any(excl.lower() in diag_lower for excl in cat_info.get('exclude', []))
                if not excluded:
                    priority = -len(kw)
                    if priority < best_priority:
                        best_priority = priority
                        best_match = cat_key
    return best_match

def extract_diagnosis(conv):
    for entry in conv.get('conversation_log', []):
        if entry.get('type') == 'terminated':
            tc = entry.get('tool_call', {})
            if tc.get('name') == 'finalize_diagnosis':
                return tc.get('arguments', {}).get('primary_diagnosis', '')
    for entry in conv.get('conversation_log', [])[::-1]:
        content = str(entry.get('content', ''))
        if '诊断' in content and len(content) > 20:
            return content[:300]
    return ''

conv_dir = str(SAVE_DIR)
TARGET = ['OLP001','PV001','OC001','RAS001','HSV001','DLE001','LEUK001','EM001','ANUG001','LR001','ATOLP001','BP001','ROM001','LEUK002','PV002','HZ001','EM002','AOU001','MRAS001','OLL001','WSN001','CC001','PIM001','MRS001']

best = {}
for fn in os.listdir(conv_dir):
    if not fn.endswith('.json'): continue
    fp = os.path.join(conv_dir, fn)
    try:
        with open(fp) as f: data = json.load(f)
    except: continue
    label = data.get('label', 'Standard')
    if label == 'Standard': continue
    hadm_id = data.get('hadm_id', '')
    if hadm_id not in TARGET: continue

    key = (hadm_id, label)
    if key not in best:
        best[key] = (fn, data)
    else:
        old_fn, old_data = best[key]
        if data.get('completed') and not old_data.get('completed'):
            best[key] = (fn, data)
        elif data.get('completed') == old_data.get('completed') and fn > old_fn:
            best[key] = (fn, data)

summary = defaultdict(lambda: {'total': 0, 'completed': 0, 'correct': 0})
for key, (fn, data) in best.items():
    hadm_id, label = key
    doc_type = label.split('_')[0]
    pat_type = '_'.join(label.split('_')[1:])
    cfg = f'{doc_type}x{pat_type}'

    summary[cfg]['total'] += 1
    if data.get('completed'):
        summary[cfg]['completed'] += 1
        diag_text = extract_diagnosis(data)
        agent_cat = normalize_diagnosis(diag_text)
        true_diag = query_table('diagnoses', hadm_id)
        true_text = true_diag.get('primary_diagnosis', '') if true_diag else ''
        true_cat = normalize_diagnosis(true_text)
        if agent_cat and true_cat and agent_cat == true_cat:
            summary[cfg]['correct'] += 1

print(f"{'配置':<28} {'总数':>4} {'完成':>4} {'完成率':>8} {'正确':>4} {'准确率':>8}")
print('-'*70)
t_all = t_comp = t_corr = 0
for cfg in sorted(summary.keys()):
    s = summary[cfg]
    t_all += s['total']; t_comp += s['completed']; t_corr += s['correct']
    cr = f'{s["completed"]/s["total"]*100:.1f}%'
    acc = f'{s["correct"]/s["completed"]*100:.1f}%' if s['completed'] > 0 else 'N/A'
    print(f'{cfg:<28} {s["total"]:>4} {s["completed"]:>4} {cr:>8} {s["correct"]:>4} {acc:>8}')
print('-'*70)
print(f'{"总计":<28} {t_all:>4} {t_comp:>4} {t_comp/t_all*100:.1f}% {t_corr:>4} {t_corr/t_comp*100:.1f}%' if t_comp>0 else '')
print(f'\nv0.1.2原版: 完成率72.8% 准确率100% 未完成40/144')
print(f'DeepRare版: 完成率{t_comp/t_all*100:.1f}% 准确率{t_corr/t_comp*100:.1f}%' if t_comp>0 else '')
