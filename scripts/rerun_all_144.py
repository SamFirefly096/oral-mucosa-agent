#!/usr/bin/env python3
"""批量重跑所有24病例x6组合=144次实验 (v0.1.2 with reflection + evidence)"""
import sys, os, time, json
from datetime import datetime
from pathlib import Path

# 设置项目路径
PROJECT_ROOT = Path('/opt/oral-mucosa-agent')
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

# 关闭thinking模式以加速（节省API时间）
os.environ['MIRA_ENABLE_THINKING'] = 'false'

from database import get_hpi_text, query_table, list_cases, create_database
from agents_enhanced import (
    LearningMedAgent, TextbookMedAgent, ChiefMedAgent,
    OriginalPatientAgent, RealisticPatientAgent,
    PatientContext
)
from conversation import run_conversation
from config import SAVE_DIR

# 确保数据库存在（如果已存在则跳过）
try:
    create_database()
except Exception:
    pass  # 数据库已存在，无需重复创建

# 6种组合配置
CONFIGS = [
    ('Learn', 'Original', LearningMedAgent, OriginalPatientAgent),
    ('Learn', 'Realistic', LearningMedAgent, RealisticPatientAgent),
    ('Textbook', 'Original', TextbookMedAgent, OriginalPatientAgent),
    ('Textbook', 'Realistic', TextbookMedAgent, RealisticPatientAgent),
    ('Chief', 'Original', ChiefMedAgent, OriginalPatientAgent),
    ('Chief', 'Realistic', ChiefMedAgent, RealisticPatientAgent),
]

# 清除所有旧的6组对比文件（保留Standard文件）
print("清理旧文件...")
old_count = 0
for fp in SAVE_DIR.glob('*.json'):
    name = fp.name
    if any(tag in name for tag in ['_Chief_', '_Lrn_', '_Txt_', '_Learn_', '_Textbook_']):
        fp.unlink()
        old_count += 1
print(f"已删除 {old_count} 个旧的6组对比文件")

# 获取所有24个病例
cases = [r[0] for r in list_cases()]
total_configs = len(CONFIGS)
total_runs = len(cases) * total_configs
print(f"共 {len(cases)} 个病例, {total_configs} 种配置, 总计 {total_runs} 次实验")

# 运行
run_count = 0
success_count = 0
fail_count = 0
start_time = time.time()

log_file = PROJECT_ROOT / 'outputs' / 'rerun_144_log.txt'

for doc_name, pat_name, DocAgentClass, PatAgentClass in CONFIGS:
    config_label = f'{doc_name}_{pat_name}'
    print(f'\n{"="*60}')
    print(f'配置: {config_label}')
    print(f'{"="*60}')

    for i, hadm_id in enumerate(cases, 1):
        run_count += 1

        # 获取患者数据
        p = query_table('patients', hadm_id)
        cc = query_table('chief_complaints', hadm_id)
        if not p or not cc:
            print(f'  [{i}/{len(cases)}] {hadm_id} SKIP (no data)')
            continue

        ctx = PatientContext(
            hadm_id=hadm_id,
            patient_info_text=get_hpi_text(hadm_id),
            age=p.get('age'),
            gender=p.get('gender'),
        )

        try:
            med = DocAgentClass(model='deepseek-v4-flash', thinking=False)
            pat = PatAgentClass(model='deepseek-v4-flash')
            pat.init_with_patient(ctx)

            t0 = time.time()
            result = run_conversation(
                med_agent=med,
                patient_agent=pat,
                patient_context=ctx,
                primary_complaint='',
                verbose=False,
                max_turns=35,  # 增加到35轮以容纳反思循环
            )
            elapsed = time.time() - t0

            # 保存（文件命名格式：HADM_Doc_Pat_timestamp.json）
            ts = time.strftime('%Y%m%d_%H%M%S')
            filename = f'{hadm_id}_{doc_name}_{pat_name}_{ts}.json'
            filepath = SAVE_DIR / filename

            output = {
                'hadm_id': hadm_id,
                'label': config_label,
                'conversation_log': result['conversation_log'],
                'statistics': result['statistics'],
                'completed': result['completed'],
            }

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2)

            s = result['statistics']
            success_count += 1

            progress_pct = success_count / total_runs * 100
            elapsed_total = time.time() - start_time
            rate = success_count / (elapsed_total / 3600) if elapsed_total > 0 else 0

            msg = (f'  [{success_count}/{total_runs} ({progress_pct:.0f}%)] '
                   f'{hadm_id} {config_label} OK '
                   f'{elapsed:.0f}s {s["total_turns"]}t/{s["tool_calls"]}tc '
                   f'(rate: {rate:.0f}/hr)')
            print(msg, flush=True)

            # 写日志
            with open(log_file, 'a', encoding='utf-8') as lf:
                lf.write(f'{datetime.now().isoformat()} {msg}\n')

        except Exception as ex:
            fail_count += 1
            msg = f'  [{run_count}/{total_runs}] {hadm_id} {config_label} FAIL: {ex}'
            print(msg, flush=True)
            with open(log_file, 'a', encoding='utf-8') as lf:
                lf.write(f'{datetime.now().isoformat()} {msg}\n')

# 最终汇总
total_elapsed = time.time() - start_time
summary = f'''
{"="*60}
批量运行完成
{"="*60}
总运行: {run_count}
成功: {success_count}
失败: {fail_count}
耗时: {total_elapsed/3600:.1f} 小时 ({total_elapsed/60:.0f} 分钟)
日志: {log_file}
{"="*60}
'''
print(summary)
with open(log_file, 'a', encoding='utf-8') as lf:
    lf.write(summary)
