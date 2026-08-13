import sys
sys.path.insert(0, '/opt/oral-mucosa-agent')
from database import create_database, get_hpi_text, query_table
from agents_enhanced import ChiefMedAgent, RealisticPatientAgent, PatientContext
from conversation_v013 import run_conversation, save_result

hadm_id = 'PV001'
cc = query_table('chief_complaints', hadm_id)
patient = query_table('patients', hadm_id)
hpi = get_hpi_text(hadm_id)
ctx = PatientContext(hadm_id=hadm_id, patient_info_text=hpi, age=patient.get('age'), gender=patient.get('gender'))
med = ChiefMedAgent(model='deepseek-v4-pro', thinking=True)
pat = RealisticPatientAgent(model='deepseek-v4-pro')
pat.init_with_patient(ctx)
result = run_conversation(med, pat, ctx, cc.get('chief_complaint',''), max_turns=40, verbose=True)
save_result(result, hadm_id)

stats = result['statistics']
print(f"""\n{'='*60}
v0.1.3 Server Test: {hadm_id} (ChiefxRealistic)
  Completed: {result['completed']}
  Turns: {stats['total_turns']}
  Tools: {stats['tool_calls']}
  Time: {stats['total_time_seconds']}s
  Version: {result.get('version', 'unknown')}
{'='*60}""")
