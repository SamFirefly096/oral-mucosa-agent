"""
工具执行器
接收 LLM 的工具调用参数，查询本地 SQLite 数据库，返回格式化结果。
基于 MIRA tool_execs.py 的架构，但去除 FHIR 层。
"""
import json
from database import query_table


def _fmt_table(name: str, row: dict) -> str:
    """将数据库行格式化为 LLM 可读的文本"""
    if not row:
        return f"[{name}] 无数据"

    items = []
    for k, v in row.items():
        if k in ("id", "hadm_id"):
            continue
        if v is None:
            continue
        # 翻译常用字段名
        label = {
            # patients
            "age": "年龄", "gender": "性别",
            "systemic_diseases": "系统性疾病", "medications": "当前用药", "allergies": "药物过敏",
            # chief_complaints
            "chief_complaint": "主诉", "symptom_onset": "发病时间",
            "symptom_duration_days": "病程(天)", "symptom_evolution": "症状演变",
            # oral_examinations
            "lesion_location": "病损部位", "lesion_morphology": "病损形态",
            "lesion_size_mm": "病损大小", "lesion_color": "病损颜色",
            "lesion_texture": "病损质地", "nikolsky_sign": "Nikolsky征",
            "extraoral_findings": "口腔外体征", "oral_hygiene": "口腔卫生",
            "additional_notes": "补充说明",
            # lab_results
            "cbc_wbc": "白细胞(×10⁹/L)", "cbc_hb": "血红蛋白(g/L)", "cbc_plt": "血小板(×10⁹/L)",
            "esr": "血沉(mm/h)", "crp": "C反应蛋白(mg/L)", "ana": "ANA",
            "anti_dsdna": "抗dsDNA(IU/mL)", "anti_desmoglein1": "抗Dsg1(U/mL)",
            "anti_desmoglein3": "抗Dsg3(U/mL)", "anti_bp180": "抗BP180(U/mL)",
            "anti_bp230": "抗BP230(U/mL)", "hiv_test": "HIV检测",
            "hba1c": "糖化血红蛋白(%)", "serum_iron": "血清铁(μmol/L)",
            "serum_folate": "叶酸(nmol/L)", "serum_b12": "维生素B12(pmol/L)",
            "tspot": "T-SPOT",
            # microbiology
            "fungal_smear": "真菌涂片", "fungal_culture": "真菌培养",
            "hsv_pcr": "HSV PCR", "vzv_pcr": "VZV PCR", "cmv_pcr": "CMV PCR",
            "bacterial_culture": "细菌培养", "hp_test": "HP检测",
            # pathology
            "biopsy_site": "活检部位", "he_findings": "HE染色", "dif_findings": "DIF",
            "iif_findings": "IIF", "pathological_diagnosis": "病理诊断",
            # diagnoses (这些在 finalize 时返回完整诊断)
            "primary_diagnosis": "主要诊断", "differential_diagnoses": "鉴别诊断",
            "icd11_code": "ICD-11", "diagnosis_category": "诊断类别",
            # treatments
            "topical_treatment": "局部治疗", "systemic_treatment": "全身治疗",
            "adjunctive_treatment": "辅助治疗", "follow_up_plan": "随访计划",
            "admission_needed": "需住院", "prognosis": "预后",
        }.get(k, k)
        items.append(f"  {label}: {v}")
    return f"[{name}]\n" + "\n".join(items)


def execute_take_history(hadm_id: str) -> str:
    """获取患者基本信息和主诉——通过对话方式获取，而非一次性返回"""
    patient = query_table("patients", hadm_id)
    cc = query_table("chief_complaints", hadm_id)

    if not patient:
        return "患者信息不可用"

    # 返回结构化但简洁的信息——Agent可以通过追问获取更多细节
    return f"""患者基本信息：
- 年龄：{patient.get('age', 'N/A')} 岁
- 性别：{'女' if patient.get('gender') == 'F' else '男'}
- 主诉：{cc.get('chief_complaint', 'N/A')}
- 发病：{cc.get('symptom_onset', 'N/A')}，病程约{cc.get('symptom_duration_days', 'N/A')}天

（可通过追问了解更多病史细节）"""


def execute_oral_examination(hadm_id: str, **_) -> str:
    """执行口腔检查——查询数据库中的检查结果"""
    exam = query_table("oral_examinations", hadm_id)
    if not exam:
        return "未找到该患者的检查记录"

    return _fmt_table("口腔黏膜专科检查结果", exam)


def execute_lab_tests(hadm_id: str, lab_tests: list[str] = None, **kwargs) -> str:
    """查询化验结果"""
    lab = query_table("lab_results", hadm_id)
    if not lab:
        return "未找到该患者的化验结果"

    # 如果指定了特定项目，只返回那些
    if lab_tests:
        # 返回全部但标注 Agent 申请了哪些
        requested = {t: lab.get(t) for t in lab_tests if t in lab}
        all_results = _fmt_table("化验结果（*为本次申请）", lab)
        return all_results
    return _fmt_table("化验结果", lab)


def execute_microbiology(hadm_id: str, micro_tests: list[str] = None, **kwargs) -> str:
    """查询微生物检查结果"""
    micro = query_table("microbiology_results", hadm_id)
    if not micro:
        return "未找到该患者的微生物检查结果"
    return _fmt_table("微生物检查结果", micro)


def execute_pathology(hadm_id: str, **kwargs) -> str:
    """查询病理检查结果"""
    path = query_table("pathology_results", hadm_id)
    if not path:
        return "该患者未进行病理活检或无活检记录"
    return _fmt_table("病理检查结果", path)


def execute_tcm_four_diagnosis(hadm_id: str, **_) -> str:
    """查询中医四诊结果"""
    tcm = query_table("tcm_four_diagnosis", hadm_id)
    if not tcm:
        return "未找到该患者的中医四诊记录"

    lines = [
        "══════════ 中医四诊 ══════════",
        "",
        "【望诊】",
        f"  {tcm.get('wang_diagnosis', 'N/A')}",
        f"  舌质：{tcm.get('tongue_body', 'N/A')}",
        f"  舌苔：{tcm.get('tongue_coating', 'N/A')}",
        f"  舌下络脉：{tcm.get('tongue_vein', 'N/A')}",
        "",
        "【闻诊】",
        f"  {tcm.get('wen_diagnosis', 'N/A')}",
        "",
        "【问诊】",
        f"  {tcm.get('wen_inquiry', 'N/A')}",
        "",
        "【切诊】",
        f"  脉象：{tcm.get('pulse_description', 'N/A')}",
        f"  {tcm.get('qie_diagnosis', 'N/A')}",
        "",
        "══════════════════════════════",
    ]
    return "\n".join(lines)


def execute_tcm_formula(hadm_id: str, **kwargs) -> str:
    """记录中药处方"""
    tcm = query_table("tcm_prescriptions", hadm_id)
    if tcm:
        ref_formula = f"\n\n参考方剂（数据库）：{tcm.get('formula_name', '')}"
    else:
        ref_formula = ""

    return f"""中药处方已记录。请确保：
1. 每味药标注剂量和特殊煎法（先煎/后下/包煎/烊化）
2. 煎服法明确（浸泡时间、煎煮次数、取汁量、服法）
3. 临证加减有明确指征
4. 中成药配合标注适应证和禁忌
{ref_formula}
（模拟环境中处方被记录但不实际执行）"""


def execute_diagnosis(hadm_id: str, **kwargs) -> str:
    """确认诊断并获取正确答案（用于评估对比）"""
    diag = query_table("diagnoses", hadm_id)
    treatment = query_table("treatments", hadm_id)

    if not diag:
        return "诊断数据不可用"

    lines = [
        "=" * 50,
        "诊断已记录。以下为数据库中存储的参考诊断：",
        _fmt_table("参考诊断", diag),
        _fmt_table("参考治疗方案", treatment),
        "=" * 50,
    ]
    return "\n".join(lines)


def execute_prescribe(hadm_id: str, **kwargs) -> str:
    """西医处方"""
    patient = query_table("patients", hadm_id)
    allergies = patient.get("allergies", "N/A") if patient else "N/A"
    treatment = query_table("treatments", hadm_id)

    lines = [
        "=" * 50,
        "西医处方已记录。",
        f"患者已知过敏史：{allergies}",
        "",
    ]

    if treatment:
        lines.append("参考治疗方案（数据库）：")
        lines.append(_fmt_table("治疗方案", treatment))

    lines.append("")
    lines.append("（模拟环境中处方被记录但不实际执行）")
    lines.append("=" * 50)
    return "\n".join(lines)


# ── 工具路由表 ──────────────────────────────────────
FUNC_MAP = {
    "perform_oral_examination": execute_oral_examination,
    "perform_tcm_four_diagnosis": execute_tcm_four_diagnosis,
    "order_lab_tests": execute_lab_tests,
    "order_microbiology": execute_microbiology,
    "order_pathology": execute_pathology,
    "prescribe_medications": execute_prescribe,
    "prescribe_tcm_formula": execute_tcm_formula,
    "finalize_diagnosis": execute_diagnosis,
}
