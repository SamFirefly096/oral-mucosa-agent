"""
从服务器 v0.1.4 对话文件中提取 AI 最终诊断，与数据库金标准比对。
v2: 修正 JSON 结构解析（conversation_log）
"""
import json, sqlite3, os, re, sys
from pathlib import Path
from collections import defaultdict

CONV_DIR = "/opt/oral-mucosa-agent/outputs/conversations"
DB_PATH = "/opt/oral-mucosa-agent/data/oral_mucosa.db"
OUTPUT = "/opt/oral-mucosa-agent/outputs/results/v014_diagnosis_comparison.json"

def load_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT p.hadm_id, d.primary_diagnosis, d.differential_diagnoses,
               d.diagnosis_category, d.diagnosis_basis,
               c.chief_complaint, c.symptom_duration_days,
               o.lesion_location, o.lesion_morphology, o.additional_notes,
               p.age, p.gender, p.systemic_diseases
        FROM patients p
        LEFT JOIN diagnoses d ON p.hadm_id = d.hadm_id
        LEFT JOIN chief_complaints c ON p.hadm_id = c.hadm_id
        LEFT JOIN oral_examinations o ON p.hadm_id = o.hadm_id
    """)
    cases = {}
    for row in cur.fetchall():
        cases[row["hadm_id"]] = dict(row)
    conn.close()
    return cases

def extract_diagnosis_from_conversation(filepath):
    """从 v0.1.4 对话 JSON 中提取 AI 最终诊断"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return {"error": f"JSON parse failed: {e}"}

    conv_log = data.get("conversation_log", [])
    if not conv_log:
        return {"error": "no conversation_log key"}

    completed = data.get("completed", None)
    stats = data.get("statistics", {})

    # 收集所有 finalize_diagnosis 条目
    diag_entries = []
    for entry in conv_log:
        role = entry.get("role", "")
        if "finalize_diagnosis" in role:
            tool_call = entry.get("tool_call", {})
            args = tool_call.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except:
                    args = {"raw": args}
            diag_entries.append({
                "turn": entry.get("turn"),
                "type": entry.get("type"),
                "diagnosis": args
            })

    if not diag_entries:
        # 没有 formal diagnosis — 检查最后几条消息
        last_messages = []
        for entry in conv_log[-3:]:
            last_messages.append({
                "turn": entry.get("turn"),
                "role": entry.get("role"),
                "content_preview": str(entry.get("content", ""))[:200]
            })
        return {
            "diagnosis": None,
            "diagnosis_text": None,
            "method": "no_finalize_diagnosis",
            "total_turns": len(conv_log),
            "total_messages": len(conv_log),
            "completed": completed,
            "last_messages": last_messages
        }

    # 取最后一次诊断提交（可能是 reflection 修正后的）
    last_diag = diag_entries[-1]
    args = last_diag["diagnosis"]

    primary = args.get("primary_diagnosis", "") or args.get("diagnosis", "")
    differentials = args.get("differential_diagnoses", [])
    if isinstance(differentials, str):
        differentials = [differentials]
    icd11 = args.get("icd11_code", "")
    tcm_disease = args.get("tcm_disease_name", "")
    tcm_syndrome = args.get("tcm_syndrome", "")
    evidence = args.get("evidence_references", [])
    diagnosis_basis_clinical = args.get("diagnosis_basis_clinical", "")
    diagnosis_basis_lab = args.get("diagnosis_basis_lab", "")
    confidence = args.get("confidence", "") or args.get("diagnosis_confidence", "")

    return {
        "diagnosis": primary,
        "differential_diagnoses": differentials,
        "icd11_code": icd11,
        "tcm_disease": tcm_disease,
        "tcm_syndrome": tcm_syndrome,
        "evidence_references": evidence,
        "diagnosis_basis_clinical": diagnosis_basis_clinical[:200] if diagnosis_basis_clinical else "",
        "diagnosis_basis_lab": diagnosis_basis_lab[:200] if diagnosis_basis_lab else "",
        "confidence": confidence,
        "method": f"finalize_diagnosis_turn{last_diag['turn']}_{last_diag['type']}",
        "num_diagnosis_submissions": len(diag_entries),
        "total_turns": len(conv_log),
        "completed": completed,
        "stats": stats,
    }

def keyword_match(ai_diag, gold_diag, gold_cat):
    """比对 AI 诊断和金标准，返回匹配结果"""
    if not ai_diag:
        return "NO_DIAGNOSIS", ""

    ai = ai_diag.replace(" ", "").replace("（","(").replace("）",")").lower()
    gd = gold_diag.replace(" ", "").replace("（","(").replace("）",")").lower()

    # 完全或包含匹配
    if ai == gd:
        return "EXACT", "完全一致"
    if gd in ai:
        return "AI_SUPERSET", "AI诊断包含金标准"
    if ai in gd:
        return "AI_SUBSET", "AI诊断是金标准的子串"

    # 按疾病类别做关键词匹配
    cat_keywords = {
        "oral_lichen_planus": ["扁平苔藓", "lichen planus", "olp"],
        "pemphigus_vulgaris": ["天疱疮", "pemphigus"],
        "oral_candidiasis": ["念珠菌", "candida", "鹅口疮"],
        "recurrent_aphthous": ["阿弗他", "aphthous", "aphtha", "ras"],
        "major_recurrent_aphthous": ["重型.*阿弗他", "major.*aphthous", "maras", "maj.*ras", "重型.*ras"],
        "herpes_simplex": ["单纯疱疹", "疱疹性龈口炎", "herpes simplex", "hsv(?!.*zoster)"],
        "discoid_lupus": ["盘状红斑狼疮", "discoid lupus", "dle"],
        "leukoplakia": ["白斑", "leukoplakia"],
        "erythema_multiforme": ["多形红斑", "erythema multiforme"],
        "anug": ["坏死性溃疡性龈炎", "anug", "necrotizing ulcerative gingivitis"],
        "lichenoid_reaction": ["苔藓样反应", "苔藓样病变", "lichenoid"],
        "oral_lichenoid_lesion": ["苔藓样病变", "lichenoid lesion"],
        "bullous_pemphigoid": ["类天疱疮", "pemphigoid", "bp(?!00)"],
        "radiation_induced_oral_mucositis": ["放射性", "radiation", "放射回忆", "mucositis"],
        "herpes_zoster": ["带状疱疹", "herpes zoster", "shingles"],
        "allergic_oral_ulceration": ["过敏性口炎", "allergic.*stomatitis", "过敏.*口炎"],
        "white_sponge_nevus": ["白色海绵状斑痣", "white sponge nevus"],
        "chronic_cheilitis": ["慢性唇炎", "chronic cheilitis"],
        "peri_implant_mucositis": ["种植体周围.*黏膜炎", "种植体周围炎", "peri.implant"],
        "melkersson_rosenthal": ["梅罗", "melkersson", "肉芽肿性唇炎"],
    }

    # 检查金标准的关键词是否在 AI 诊断中出现
    if gold_cat in cat_keywords:
        keywords = cat_keywords[gold_cat]
        for kw in keywords:
            if re.search(kw, ai):
                return "KEYWORD_MATCH", f"关键词匹配: {kw}"

    # 检查 AI 诊断是否匹配了某个 OTHER 类别（即误诊）
    for cat, keywords in cat_keywords.items():
        if cat == gold_cat:
            continue
        for kw in keywords:
            if re.search(kw, ai):
                return "MISMATCH_TO_" + cat.upper(), f"AI可能误诊为: {cat} (匹配关键词: {kw})"

    return "UNCLEAR", "无法自动判断"

def main():
    cases = load_db()
    print(f"已加载 {len(cases)} 个数据库病例")

    conv_files = sorted(Path(CONV_DIR).glob("*_v014_*.json"))
    print(f"找到 {len(conv_files)} 个 v0.1.4 对话文件")

    results = []
    for fp in conv_files:
        fname = fp.name
        if fname.startswith("batch") or fname.startswith("MRAS001_v014_summary"):
            continue

        # 解析 label
        parts = fname.replace(".json", "").split("_")
        hadm_id = parts[0]
        # 在 v014 之前的部分是 label
        label_parts = []
        for i, p in enumerate(parts[1:], 1):
            if p == "v014":
                break
            label_parts.append(p)
        label = "_".join(label_parts) if label_parts else "unknown"

        diag_info = extract_diagnosis_from_conversation(str(fp))
        gold = cases.get(hadm_id, {})

        ai_diag = diag_info.get("diagnosis") if isinstance(diag_info, dict) else None
        gold_diag = gold.get("primary_diagnosis", "")
        gold_cat = gold.get("diagnosis_category", "")

        match_result, match_detail = keyword_match(ai_diag, gold_diag, gold_cat)

        entry = {
            "file": fname,
            "hadm_id": hadm_id,
            "label": label,
            "ai_diagnosis": ai_diag,
            "ai_differential": diag_info.get("differential_diagnoses", []) if isinstance(diag_info, dict) else [],
            "ai_icd11": diag_info.get("icd11_code", "") if isinstance(diag_info, dict) else "",
            "ai_tcm_disease": diag_info.get("tcm_disease", "") if isinstance(diag_info, dict) else "",
            "ai_tcm_syndrome": diag_info.get("tcm_syndrome", "") if isinstance(diag_info, dict) else "",
            "ai_confidence": diag_info.get("confidence", "") if isinstance(diag_info, dict) else "",
            "ai_diagnosis_basis": (diag_info.get("diagnosis_basis_clinical", "") + " | " + diag_info.get("diagnosis_basis_lab", "")) if isinstance(diag_info, dict) else "",
            "extraction_method": diag_info.get("method", "error") if isinstance(diag_info, dict) else str(diag_info),
            "num_diagnosis_submissions": diag_info.get("num_diagnosis_submissions", 0) if isinstance(diag_info, dict) else 0,
            "total_turns": diag_info.get("total_turns", 0) if isinstance(diag_info, dict) else 0,
            "completed": diag_info.get("completed", None) if isinstance(diag_info, dict) else None,
            "stats": diag_info.get("stats", {}) if isinstance(diag_info, dict) else {},
            "gold_diagnosis": gold_diag,
            "gold_differential": gold.get("differential_diagnoses", ""),
            "gold_category": gold_cat,
            "gold_diagnosis_basis": gold.get("diagnosis_basis", ""),
            "chief_complaint": (gold.get("chief_complaint") or "")[:120],
            "lesion_location": gold.get("lesion_location", ""),
            "age": gold.get("age", ""),
            "gender": gold.get("gender", ""),
            "systemic_diseases": gold.get("systemic_diseases", ""),
            "match_result": match_result,
            "match_detail": match_detail,
        }
        results.append(entry)

    # 统计
    no_diag = [r for r in results if r["ai_diagnosis"] is None]
    with_diag = [r for r in results if r["ai_diagnosis"] is not None]
    exact = [r for r in with_diag if r["match_result"] == "EXACT"]
    keyword_ok = [r for r in with_diag if r["match_result"] in ("EXACT", "AI_SUPERSET", "AI_SUBSET", "KEYWORD_MATCH")]
    mismatch = [r for r in with_diag if r["match_result"].startswith("MISMATCH")]
    unclear = [r for r in with_diag if r["match_result"] == "UNCLEAR"]

    print(f"\n=== 统计 ===")
    print(f"总文件数: {len(results)}")
    print(f"有诊断: {len(with_diag)}")
    print(f"无诊断: {len(no_diag)}")
    print(f"完全匹配: {len(exact)}")
    print(f"关键词匹配(含完全): {len(keyword_ok)}")
    print(f"可能误诊: {len(mismatch)}")
    print(f"无法自动判断: {len(unclear)}")

    print(f"\n=== 可能误诊列表 ===")
    for r in mismatch:
        print(f"  {r['label']}: AI='{r['ai_diagnosis']}' vs Gold='{r['gold_diagnosis']}' [{r['match_detail']}]")

    print(f"\n=== 无诊断列表 ===")
    for r in no_diag:
        print(f"  {r['label']} ({r['hadm_id']}): {r['extraction_method']}")

    # 输出
    output = {
        "summary": {
            "total_files": len(results),
            "with_diagnosis": len(with_diag),
            "without_diagnosis": len(no_diag),
            "exact_match": len(exact),
            "keyword_match_total": len(keyword_ok),
            "likely_mismatch": len(mismatch),
            "unclear": len(unclear),
        },
        "mismatches": [r for r in mismatch],
        "no_diagnosis": [r for r in no_diag],
        "unclear": [r for r in unclear],
        "all_results": results,
    }

    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n输出已写入 {OUTPUT}")

if __name__ == "__main__":
    main()
