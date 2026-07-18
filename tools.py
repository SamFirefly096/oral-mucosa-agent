"""
口腔黏膜病 AI Agent 工具集
基于 MIRA 架构，适配 DeepSeek Function Calling。
每个工具都是 Pydantic BaseModel，自动生成 JSON Schema 供 LLM 调用。
"""
import json
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── 共享枚举 ──────────────────────────────────────
class LesionLocation(str, Enum):
    buccal_mucosa = "buccal_mucosa"
    labial_mucosa = "labial_mucosa"
    lip_vermilion = "lip_vermilion"
    tongue_dorsal = "tongue_dorsal"
    tongue_ventral = "tongue_ventral"
    tongue_lateral = "tongue_lateral"
    palate_hard = "palate_hard"
    palate_soft = "palate_soft"
    gingiva = "gingiva"
    floor_of_mouth = "floor_of_mouth"
    oropharynx = "oropharynx"
    perioral_skin = "perioral_skin"


class LesionMorphology(str, Enum):
    macule = "macule"
    plaque = "plaque"
    erosion = "erosion"
    ulcer = "ulcer"
    vesicle = "vesicle"
    bulla = "bulla"
    reticular = "reticular"
    atrophic = "atrophic"
    pseudomembrane = "pseudomembrane"
    crust = "crust"
    necrosis = "necrosis"


class LabValue(str, Enum):
    cbc_wbc = "cbc_wbc"
    cbc_hb = "cbc_hb"
    cbc_plt = "cbc_plt"
    esr = "esr"
    crp = "crp"
    ana = "ana"
    anti_dsdna = "anti_dsdna"
    anti_desmoglein_1 = "anti_desmoglein_1"
    anti_desmoglein_3 = "anti_desmoglein_3"
    anti_bp180 = "anti_bp180"
    anti_bp230 = "anti_bp230"
    hiv_test = "hiv_test"
    hba1c = "hba1c"
    serum_iron = "serum_iron"
    serum_folate = "serum_folate"
    serum_b12 = "serum_b12"
    tspot = "tspot"


class MicroTest(str, Enum):
    fungal_smear = "fungal_smear"
    fungal_culture = "fungal_culture"
    hsv_pcr = "hsv_pcr"
    vzv_pcr = "vzv_pcr"
    cmv_pcr = "cmv_pcr"
    bacterial_culture = "bacterial_culture"


class MedicationRoute(str, Enum):
    topical = "topical"
    oral = "oral"
    intravenous = "intravenous"
    intramuscular = "intramuscular"
    sublingual = "sublingual"


class AdmDecision(str, Enum):
    admit = "admit"
    discharge = "discharge"
    observe = "observe"


# ── 工具定义 ──────────────────────────────────────
class PatientHistory(BaseModel):
    """采集患者口腔相关病史"""
    tool_name: str = Field(default="take_oral_history", description="工具名称")

    chief_complaint: str = Field(
        description="患者主诉（由患者Agent根据数据库回复）"
    )
    symptom_onset: str = Field(
        description="发病时间和诱因"
    )
    symptom_duration_days: Optional[int] = Field(
        default=None, description="症状持续时间（天）"
    )
    symptom_evolution: str = Field(
        description="症状演变过程"
    )
    medical_history: str = Field(
        description="系统性疾病史（糖尿病、高血压、免疫病等）"
    )
    current_medications: str = Field(
        description="当前用药（处方药、非处方药、中药）"
    )
    allergies: str = Field(
        description="药物过敏史"
    )
    social_history: str = Field(
        description="吸烟、饮酒、槟榔咀嚼等习惯"
    )


class OralExamination(BaseModel):
    """执行口腔黏膜专科检查"""
    tool_name: str = Field(default="perform_oral_examination", description="工具名称")

    lesion_location: list[str] = Field(
        description="病损部位",
        examples=[["buccal_mucosa", "tongue_lateral"]],
    )
    lesion_morphology: list[str] = Field(
        description="病损形态",
        examples=[["reticular", "erosion"]],
    )
    lesion_size: str = Field(
        description="病损大小范围",
        examples=["0.8x1.2cm"],
    )
    lesion_color: str = Field(
        description="病损颜色特征",
    )
    lesion_texture: str = Field(
        description="病损质地（光滑/粗糙/脆性/硬结等）",
    )
    nikolsky_sign: str = Field(
        description="Nikolsky征：positive/negative/not_tested",
        examples=["negative"],
    )
    extraoral_findings: str = Field(
        description="口腔外体征（皮疹/眼病变/生殖器溃疡/淋巴结等）",
    )
    oral_hygiene: str = Field(
        description="口腔卫生状况：good/fair/poor",
    )
    additional_notes: Optional[str] = Field(
        default=None, description="其他值得注意的口腔检查发现"
    )


class LabRequest(BaseModel):
    """申请化验检查（可多选）"""
    tool_name: str = Field(default="order_lab_tests", description="工具名称")

    lab_tests: list[str] = Field(
        description="需要申请的化验项目",
        examples=[["cbc_wbc", "esr", "crp", "ana"]],
    )
    rationale: str = Field(
        description="申请这些化验的临床理由",
    )


class MicrobiologyRequest(BaseModel):
    """申请微生物检查（可多选）"""
    tool_name: str = Field(default="order_microbiology", description="工具名称")

    micro_tests: list[str] = Field(
        description="需要申请的微生物检查项目",
        examples=[["fungal_smear", "hsv_pcr"]],
    )
    rationale: str = Field(
        description="申请微生物检查的临床理由",
    )


class PathologyRequest(BaseModel):
    """申请病理活检"""
    tool_name: str = Field(default="order_pathology", description="工具名称")

    biopsy_site: str = Field(
        description="建议活检部位",
        examples=["right_buccal_mucosa_perilesional"],
    )
    stains_requested: Optional[list[str]] = Field(
        default=None,
        description="需要的特殊染色：['HE','PAS','DIF','IIF']",
    )
    rationale: str = Field(
        description="活检的临床指征",
    )


class MedicationPrescription(BaseModel):
    """开具处方——单项药物"""
    drug_name: str = Field(description="药物名称")
    dosage: str = Field(description="剂量（如 0.1%, 20mg, 100000U）")
    frequency: str = Field(description="频率（如 bid, tid, qd, qid）")
    route: str = Field(description="给药途径", examples=["topical", "oral"])
    duration: str = Field(description="疗程（如 7d, 2w, taper）")
    notes: Optional[str] = Field(default=None, description="用药备注")


class MedicationRequest(BaseModel):
    """开具处方（可包含多种药物）"""
    tool_name: str = Field(default="prescribe_medications", description="工具名称")

    topical_medications: list[MedicationPrescription] = Field(
        default_factory=list, description="局部用药"
    )
    systemic_medications: list[MedicationPrescription] = Field(
        default_factory=list, description="全身用药"
    )
    supportive_care: Optional[str] = Field(
        default=None,
        description="支持治疗建议（补液/营养/口腔护理等）",
    )
    drug_allergy_check: str = Field(
        description="确认已核查患者药物过敏史: 'checked - no known allergies' 或 'checked - allergic to [X] - avoided'",
    )
    renal_hepatic_check: Optional[str] = Field(
        default=None,
        description="肾功能/肝功能剂量调整确认",
    )


class TCMPrescription(BaseModel):
    """中药处方——单项药物"""
    herb_name: str = Field(description="中药名称")
    dosage: str = Field(description="剂量（如 10g, 15g, 6枚）")
    special_preparation: Optional[str] = Field(
        default=None,
        description="特殊煎法：先煎/后下/包煎/烊化/冲服/另炖",
        examples=["后下", "先煎", "包煎"],
    )


class PatentMedicine(BaseModel):
    """中成药"""
    name: str = Field(description="中成药名称")
    dosage: str = Field(description="剂量")
    frequency: str = Field(description="用法频率")
    note: Optional[str] = Field(default=None, description="备注（适应证/禁忌）")


class TCMFourDiagnosis(BaseModel):
    """获取中医四诊（望闻问切）结果"""
    tool_name: str = Field(default="perform_tcm_four_diagnosis", description="工具名称")


class TCMFormulaRequest(BaseModel):
    """开具中药处方（可包含内服+外治）"""
    tool_name: str = Field(default="prescribe_tcm_formula", description="工具名称")

    formula_name: str = Field(
        description="方剂名称（含证型导向）",
        examples=["丹栀逍遥散合桃红四物汤加减", "甘草泻心汤合导赤散加减"],
    )
    herbs: list[TCMPrescription] = Field(
        description="中药组成（每味药名+剂量+特殊煎法）",
    )
    preparation_method: str = Field(
        description="煎服法",
        examples=["每日1剂，加水浸泡30分钟，武火煮沸后文火煎30分钟，取汁200ml；二煎取汁150ml。两煎混合，分早晚两次温服。"],
    )
    modifications: Optional[list[str]] = Field(
        default=None,
        description="临证加减要点（常用加减变化）",
    )
    patent_medicines: Optional[list[PatentMedicine]] = Field(
        default=None,
        description="配合的中成药",
    )
    external_treatment: Optional[str] = Field(
        default=None,
        description="中医外治法（含漱/外敷/针灸/耳穴等）",
    )
    treatment_principle: str = Field(
        description="治则治法",
        examples=["疏肝理气，活血化瘀，兼清湿热"],
    )


class SearchClinicalKnowledge(BaseModel):
    """查询2025口腔黏膜病学术年会诊疗知识库，获取最新的诊疗经验、专家意见、鉴别诊断要点和罕见病识别特征。
    在以下情况应主动调用此工具：(1)遇到罕见或少见病临床表现需确认诊断线索；
    (2)治疗方案不确定需查阅最新临床经验；(3)需要了解特定疾病的最新治疗技术或药物进展。
    此工具按关键词检索286条知识条目，返回最相关的内容摘要。"""
    tool_name: str = Field(default="search_clinical_knowledge", description="工具名称")

    query: str = Field(
        description="搜索关键词（疾病名称、症状、治疗方法、药物名称等，中文优先）",
        examples=["天疱疮 利妥昔单抗", "腭部溃疡 鉴别诊断", "OLP维A酸方案"],
    )
    knowledge_type: Optional[str] = Field(
        default=None,
        description="可选过滤：专家意见/诊疗经验/鉴别诊断/技术创新/临床警示/罕见病识别要点/病例发现/罕见病知识/治疗方案/诊断路径",
        examples=["专家意见", "诊疗经验", "鉴别诊断"],
    )
    top_k: int = Field(
        default=5, ge=1, le=10,
        description="返回最相关的结果数量（1-10，默认5）",
    )


class DiagnosisAndPlan(BaseModel):
    """完成诊断并制定治疗计划——此工具调用后对话结束"""
    tool_name: str = Field(default="finalize_diagnosis", description="工具名称")

    # 西医诊断
    primary_diagnosis: str = Field(
        description="西医主要诊断（完整诊断名称）",
    )
    icd11_code: Optional[str] = Field(default=None, description="ICD-11编码")
    differential_diagnoses: list[str] = Field(
        description="鉴别诊断列表（至少2-3个）",
    )
    diagnosis_basis_clinical: str = Field(description="诊断的临床依据")
    diagnosis_basis_lab: Optional[str] = Field(default=None, description="诊断的化验/微生物/病理依据")

    # 中医诊断
    tcm_disease_name: Optional[str] = Field(
        default=None,
        description="中医病名：口癣/口疮/鹅口疮/舌痛症/唇风/猫眼疮/火赤疮/口痹/燥证",
    )
    tcm_syndrome: Optional[str] = Field(
        default=None,
        description="辨证分型：如肝郁气滞证/脾胃湿热证/阴虚火旺证等",
    )
    tcm_syndrome_basis: Optional[str] = Field(
        default=None,
        description="辨证依据（四诊合参分析）",
    )

    # 治疗方案
    admission_needed: str = Field(description="是否需要住院：yes/no")
    admission_reason: Optional[str] = Field(default=None, description="如需住院，说明理由")
    western_treatment_summary: str = Field(description="西医治疗方案总结")
    tcm_treatment_summary: Optional[str] = Field(default=None, description="中医治疗方案总结（含治则+方药+外治）")
    follow_up_plan: str = Field(description="随访计划")
    prognosis: Optional[str] = Field(default=None, description="预后评估")


# ── 所有工具列表（不含 PatientHistory — 对话开始时自动提供） ──
ALL_TOOLS = [
    SearchClinicalKnowledge,
    OralExamination,
    TCMFourDiagnosis,
    LabRequest,
    MicrobiologyRequest,
    PathologyRequest,
    MedicationRequest,
    TCMFormulaRequest,
    DiagnosisAndPlan,
]

# PatientHistory 在初始对话时自动注入，不作为 LLM 可调用工具
# 因为病史采集通过对话方式进行（与 Patient Agent 交流），
# 而非工具调用。这更接近 MIRA 的设计模式。
