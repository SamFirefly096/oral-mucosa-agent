"""
添加临床真实病例（已脱敏）：种植体周围黏膜炎、梅罗综合征
运行：python add_clinical_cases.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "oral_mucosa.db"

CLINICAL_CASES = [
    # ===== 病例1: 种植体周围黏膜炎伴溃疡 =====
    {
        "hadm_id": "PIM001",
        "patient": (49, "M",
            '["chronic_sinusitis","dental_implant_8yrs_ago"]',
            "中草药汤剂（瓜蒌薤白半夏汤加减，2026-01起间断服用）", "否认"),
        "chief_complaint": (
            "左上种植牙周围牙龈溃烂伴微痛3周",
            "3周前左上种植牙牙龈出现大范围溃疡",
            21,
            "8年前行左上大门牙种植修复。3周前无明显诱因出现种植体周围牙龈大范围溃疡，微痛。曾于外院就诊，1周前行病理活检提示"黏膜溃疡伴炎性肉芽组织形成"。溃疡持续存在近5个月未愈。平素汗出偏多，口干口苦口粘，心烦急躁，手脚心热，胸闷，偶胃胀、烧心反酸，疲乏明显，大便干。2026-01-22曾服中药后约1周出现口腔溃疡。"
        ),
        "oral_exam": (
            "maxillary_left_anterior_implant_surrounding,labial,palatal",
            "ulcer_extensive,erosion,edema,pseudomembrane,erythema",
            "唇侧约15×15mm，腭侧5×5mm水肿区",
            "表面黄白色伪膜，周围充血",
            "基底触质软，活动度良好；种植体螺纹已暴露",
            "not_tested",
            "none",
            "poor",
            "种植修复体周围唇腭侧环绕种植体大范围溃疡。唇侧可见缝合线痕。种植体唇侧探诊深度约5-6mm。口腔卫生差，菌斑软垢大量，牙石(++)。"
        ),
        "lab": (None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None),
        "micro": (None, None, None, None, None, None, None),
        "pathology": (
            "maxillary_left_anterior_implant_gingiva",
            "黏膜溃疡伴炎性肉芽组织形成，炎症较重",
            None,
            None,
            "黏膜溃疡伴炎性肉芽组织形成（建议免疫组化进一步评估）"
        ),
        "diagnosis": (
            "种植体周围黏膜炎伴溃疡 (Peri-implant Mucositis with Ulceration)",
            '["种植体周围炎","口腔扁平苔藓(糜烂型)","创伤性溃疡","过敏性口炎"]',
            "DA0C.3",
            "peri_implant_mucositis",
            '{"clinical":"种植体周围环状溃疡+探诊深度5-6mm+螺纹暴露+口腔卫生差","pathology":"黏膜溃疡伴炎性肉芽组织","time_course":"持续近5月未愈","trigger":"1-22中药方服后约1周出现(时间关联)"}'
        ),
        "treatment": (
            '{"cetylpyridinium_chloride_mouthwash":"5-15ml gargle tid","kangfuxin_liquid":"5-10ml topical tid","yangyin_shengji_powder":"topical prn"}',
            '{"none":"no systemic antibiotics indicated"}',
            '{"local_debridement":"拆线+局部冲洗+激光照射治疗","oral_hygiene_instruction":"口腔卫生指导","dietary_advice":"忌辛辣刺激食物，戒烟酒","stress_management":"放松心情，规律作息"}',
            "每1-2周复诊。治疗5周后唇侧溃疡减轻但腭侧加重，改用清热解毒方。需长期随访排除种植体失败",
            "no",
            "种植体周围黏膜炎若控制不佳可能进展为种植体周围炎(BOP+/PD≥6mm/骨吸收)。本例病程长(>5月)需警惕种植体失败风险。口腔卫生差是主要危险因素。"
        ),
    },
    # ===== 病例2: 梅罗综合征（完全型）=====
    {
        "hadm_id": "MRS001",
        "patient": (34, "M",
            '["none"]',
            "氯雷他定 10mg qd; 维生素B1 10mg tid; 维生素B6 10mg tid; 维生素B12 25μg tid", "否认"),
        "chief_complaint": (
            "口腔溃疡伴上唇肿胀3周",
            "3周前无明显诱因出现左侧颊部溃疡，随后上唇肿胀进行性加重",
            21,
            "3周前无明显诱因出现左侧颊部溃疡，当地医院予静脉输液及外用药物（具体不详），随后出现上唇肿胀呈进行性加重，累及左侧眼睑。自觉胸胁胀痛，口苦咽干，食欲不振，大便不畅。否认痤疮样皮疹、结节性红斑等。发病以来精神压力较大，情绪抑郁，善太息。否认反复口腔溃疡史。"
        ),
        "oral_exam": (
            "upper_lip_diffuse,lower_lip,left_buccal_mucosa,tongue_dorsum,left_periorbital",
            "swelling_diffuse_macrocheilia,ulcer,erosion,fissured_tongue,angular_cheilitis",
            "上唇弥漫性肿胀增厚；左颊溃疡约2×1.5cm",
            "上唇正常肤色；颊溃疡表面黄白伪膜，周围充血",
            "唇部肿胀柔软有弹性，指压无凹陷（非凹陷性水肿）；溃疡基底软",
            "not_tested",
            "right_eyelid_closure_incomplete,right_nasolabial_fold_shallow,facial_nerve_mild_dysfunction",
            "fair",
            "上唇弥漫性肿胀增厚呈'巨唇样'外观，质地柔软有弹性，指压无凹陷。肿胀累及左侧眼睑区。右侧口角糜烂。右侧眼裂闭合略受限，鼻唇沟略浅——提示轻度面神经功能障碍（颞支/颧支/颊支）。舌背中央纵行裂纹（沟纹舌）。口腔卫生一般，牙石(++)。"
        ),
        "lab": (None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None),
        "micro": (None, None, None, None, None, None, None),
        "pathology": (
            "upper_lip",
            "（建议行唇部活检：非干酪样肉芽肿性炎为MRS特征性病理改变。本案患者未行活检——为不足之处）",
            None,
            None,
            "临床诊断为主，病理待完善"
        ),
        "diagnosis": (
            "梅罗综合征，完全型，面神经轻度受累 (Melkersson-Rosenthal Syndrome, Complete Type, Mild Facial Nerve Involvement)",
            '["血管神经性水肿","克罗恩病相关性口面部肉芽肿病","结节病","贝尔面瘫","多形红斑"]',
            "DA04.2",
            "melkersson_rosenthal_syndrome",
            '{"clinical":"三联征俱备:①口面部复发性肿胀(巨唇+眼睑)②沟纹舌(舌背纵行裂纹)③面神经麻痹(右眼裂闭合不全+鼻唇沟浅)","classification":"Hornstein完全型(典型三联征仅见于8-25%MRS)","TCM_dynamic":"肝郁蕴热→风湿热毒兼肝郁脾虚→肝郁脾虚→肝脾渐和"}'
        ),
        "treatment": (
            '{"erythromycin_ointment":"bid topical to angular cheilitis","kangfuxin_liquid":"gargle tid 3-5min"}',
            '{"loratadine":"10mg qd po (患者拒用激素)","vitamin_B_complex":"B1 10mg+B6 10mg+B12 25μg tid po"}',
            '{"TCM_herbal_medicine":"逍遥散合五味消毒饮加减→柴芍六君子汤加减(动态调方,详见表2)","TCM_patent":"疏风解毒颗粒 bid→qd→停用","lifestyle":"避免辛辣刺激，戒烟限酒，规律作息，情志调摄"}',
            "治疗2周后溃疡愈合、唇肿减轻；6周后唇肿基本消退。后续每2-4周随访。建议完善：唇部活检、消化科结肠镜(排除克罗恩病)、胸部影像学(排除结节病)",
            "no",
            "MRS为罕见慢性复发性疾病(发病率~0.08%)，无法根治但可控制。糖皮质激素为一线(有效率50-80%)，本案因患者拒用改用抗组胺+中医方案效果良好。MRS与克罗恩病存在潜在关联(10-20%OFG最终确诊CD)。"
        ),
    },
]

# ── TCM四诊+辨证+处方数据 ─────────────────────────
TCM_CLINICAL = {
    "PIM001": {
        "four_diag": (
            "左上种植体周围环状大范围溃疡，表面黄白伪膜，周围充血，螺纹暴露。舌质暗，苔薄白。面色正常。",
            "无特殊口臭。",
            "口干口苦口粘，心烦急躁，手脚心热(五心烦热)，胸闷，偶胃胀、烧心反酸。疲乏明显，大便干，小便正常。汗出偏多。眠差易醒。",
            "脉弦（6-2会诊）；脉沉细（4-28记录）。",
            "暗", "薄白", "正常", "弦/沉细（随病程变化）"
        ),
        "tcm_diag": (
            "口疮（种植体周围型）", "痰瘀互结，阴虚火旺证",
            "胸闷、痰多、舌暗苔薄白为痰瘀互结；五心烦热、口干、疲乏、脉细数为阴虚火旺。1-22方（含肉桂温燥）服后出现口腔溃疡，提示温补助火加重阴虚。病位在脾肾，虚实夹杂。",
            "先以清热凉血解毒为主（5-14方），兼顾养阴生肌；后期滋阴降火、健脾益气善后"
        ),
        "tcm_rx": (
            "清热解毒方（自拟方，5-14韩燕）",
            '[{"herb":"连翘","dosage":"15g"},{"herb":"板蓝根","dosage":"15g"},{"herb":"桔梗","dosage":"10g"},{"herb":"黄芩片","dosage":"12g"},{"herb":"北柴胡","dosage":"10g"},{"herb":"升麻","dosage":"6g"},{"herb":"陈皮","dosage":"10g"},{"herb":"甘草片","dosage":"6g"},{"herb":"大黄","dosage":"10g"},{"herb":"金银花","dosage":"15g"},{"herb":"穿心莲","dosage":"10g"},{"herb":"漏芦","dosage":"10g"},{"herb":"苦地丁","dosage":"10g"},{"herb":"赤芍","dosage":"10g"},{"herb":"茯神","dosage":"10g"}]',
            "每日1剂，加水浸泡30分钟，武火煮沸后文火煎30分钟，取汁200ml；二煎取汁150ml。两煎混合，分早晚两次温服。共7剂。",
            '[{"condition":"服后乏力、大便稀（脾胃虚弱不耐苦寒）","mod":"停药观察，大便恢复正常后可减苦寒药量（大黄减至6g、去穿心莲/漏芦/苦地丁）"},{"condition":"五心烦热、口干明显（阴虚火旺）","mod":"加生地黄15g、知母10g、牡丹皮15g，减大黄"},{"condition":"胸闷持续（痰瘀未解）","mod":"加瓜蒌皮15g、薤白10g、法半夏10g"}]',
            '[{"name":"康复新液","dosage":"5-10ml","frequency":"tid","note":"含漱3-5分钟，促进黏膜愈合"},{"name":"养阴生肌散","dosage":"适量","frequency":"bid","note":"涂敷溃疡面"}]',
            "西吡氯铵含漱液5-15ml含漱tid。局部冲洗+激光照射治疗。",
            "地仓、颊车、合谷、足三里、三阴交、太溪（平补平泻）"
        ),
    },
    "MRS001": {
        "four_diag": (
            "上唇弥漫性肿胀呈'巨唇样'，右侧口角糜烂，左侧眼睑肿胀。舌背中央纵行裂纹（沟纹舌），菌状乳头充血发红。舌质暗→淡红（随治疗好转），苔薄黄→薄白。面色正常，情绪抑郁貌。",
            "语声正常，善太息。",
            "胸胁胀痛，口苦咽干，食欲不振，大便不畅。精神压力较大，情绪抑郁。否认腹痛、腹泻、便血。",
            "脉弦→略弦→和缓（随治疗好转）。",
            "暗→淡红", "薄黄→薄白", "正常", "弦→略弦"
        ),
        "tcm_diag": (
            "口疳（梅罗综合征口腔表现）", "肝郁蕴热证→风湿热毒证兼肝郁脾虚证→肝郁脾虚证（动态演变）",
            "初诊：精神压力大、善太息、胸胁胀痛、脉弦为肝郁；口苦咽干、苔薄黄为郁而化热。复诊1：唇肿反复、口角糜烂为风湿热毒；舌转淡、苔薄白为脾虚。复诊2-3：邪去正虚，肝脾渐和。《内经》'木郁达之'为治则总纲。",
            "疏肝解郁、清热解毒→祛风除湿兼健脾→健脾疏肝善后（随证动态调方）"
        ),
        "tcm_rx": (
            "逍遥散合五味消毒饮加减→柴芍六君子汤加减（分阶段）",
            '[{"herb":"柴胡","dosage":"9g"},{"herb":"白芍","dosage":"12g"},{"herb":"白术","dosage":"12g"},{"herb":"茯苓","dosage":"15g"},{"herb":"牡丹皮","dosage":"9g"},{"herb":"黄芩","dosage":"9g"},{"herb":"金银花","dosage":"15g"},{"herb":"紫花地丁","dosage":"12g"},{"herb":"甘草","dosage":"6g"},{"herb":"薄荷","dosage":"6g","special":"后下"},{"herb":"生姜","dosage":"3片"}]',
            "每日1剂，加水浸泡30分钟，武火煮沸后文火煎30分钟，取汁200ml；二煎取汁150ml。两煎混合，分早晚两次温服。",
            '[{"condition":"唇肿反复、湿邪明显（复诊1）","mod":"加防风9g、薏苡仁20g，去金银花、紫花地丁"},{"condition":"邪去正虚、脾气不足（复诊2-3）","mod":"转为柴芍六君子汤加减：柴胡9g、白芍12g、党参12g、白术12g、茯苓15g、陈皮9g、法半夏9g、甘草6g、牡丹皮9g"},{"condition":"善后调理（复诊3后）","mod":"逍遥散加减：柴胡9g、白芍12g、当归9g、白术12g、茯苓15g、薄荷6g(后下)、甘草6g、生姜3片"}]',
            '[{"name":"疏风解毒颗粒","dosage":"1袋","frequency":"bid→qd→停用","note":"西苑医院院内制剂，京卫药制字[087]第F-558号，贯穿急性期与缓解期"}]',
            "康复新液适量含漱tid，每次3-5分钟。红霉素软膏bid涂布口角糜烂处。",
            "太冲、合谷、足三里、三阴交、地仓、颊车（平补平泻，疏肝理气为主）"
        ),
    },
}


def add_cases():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    existing = set()
    cursor.execute("SELECT hadm_id FROM patients")
    for row in cursor.fetchall():
        existing.add(row[0])

    added = 0
    for case in CLINICAL_CASES:
        hadm_id = case["hadm_id"]
        if hadm_id in existing:
            print(f"  跳过: {hadm_id} (已存在)")
            continue

        cursor.execute("INSERT INTO patients VALUES (NULL,?,?,?,?,?,?)",
            (hadm_id, *case["patient"]))
        cursor.execute("INSERT INTO chief_complaints VALUES (NULL,?,?,?,?,?)",
            (hadm_id, *case["chief_complaint"]))
        cursor.execute("INSERT INTO oral_examinations VALUES (NULL,?,?,?,?,?,?,?,?,?,?)",
            (hadm_id, *case["oral_exam"]))
        cursor.execute("INSERT INTO lab_results VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (hadm_id, *case["lab"]))
        cursor.execute("INSERT INTO microbiology_results VALUES (NULL,?,?,?,?,?,?,?,?)",
            (hadm_id, *case["micro"]))
        cursor.execute("INSERT INTO pathology_results VALUES (NULL,?,?,?,?,?,?)",
            (hadm_id, *case["pathology"]))
        cursor.execute("INSERT INTO diagnoses VALUES (NULL,?,?,?,?,?,?)",
            (hadm_id, *case["diagnosis"]))
        cursor.execute("INSERT INTO treatments VALUES (NULL,?,?,?,?,?,?,?)",
            (hadm_id, *case["treatment"]))

        # TCM data
        tcm = TCM_CLINICAL.get(hadm_id, {})
        if tcm:
            fd = tcm.get("four_diag", ("", "", "", "", "", "", "", ""))
            cursor.execute("INSERT INTO tcm_four_diagnosis VALUES (NULL,?,?,?,?,?,?,?,?,?)",
                (hadm_id, *fd))
            td = tcm.get("tcm_diag", ("", "", "", ""))
            cursor.execute("INSERT INTO tcm_diagnoses VALUES (NULL,?,?,?,?,?)",
                (hadm_id, *td))
            tr = tcm.get("tcm_rx", ("", "", "", "", "", "", ""))
            cursor.execute("INSERT INTO tcm_prescriptions VALUES (NULL,?,?,?,?,?,?,?,?)",
                (hadm_id, *tr))

        print(f"  OK: {hadm_id} — {case['diagnosis'][0][:60]}")
        added += 1

    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM patients")
    total = cursor.fetchone()[0]
    print(f"\n总计: {total} 例 (新增 {added})")

    # List all
    cursor.execute("""
        SELECT p.hadm_id, p.age, p.gender, d.primary_diagnosis, d.diagnosis_category
        FROM patients p JOIN diagnoses d ON p.hadm_id = d.hadm_id ORDER BY p.id
    """)
    for row in cursor.fetchall():
        g = '女' if row[2] == 'F' else '男'
        print(f"  {row[0]:<12} {row[1]}岁 {g}  [{row[4]:<36}] {row[3][:60]}")

    conn.close()
    print("\n完成。")


if __name__ == "__main__":
    add_cases()
