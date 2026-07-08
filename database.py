"""
口腔黏膜病数据库 — 中西医结合版
SQLite 实现，含 12 例典型病例示例数据。
每个病例包含完整的临床路径：
主诉 → 病史 → 口腔检查 → 辅助检查 → 诊断 → 治疗
+ 中医四诊（望闻问切）+ 辨证分型 + 中药处方
参考：徐治鸿《中西医结合口腔黏膜病学》+ 王雨田《黏膜科轮转学生病历书写建议 v1.2》
"""
import json
import sqlite3
from pathlib import Path
from config import DATABASE_PATH

DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── 表结构 ────────────────────────────────────────
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY,
    hadm_id TEXT UNIQUE NOT NULL,
    age INTEGER,
    gender TEXT,
    systemic_diseases TEXT,       -- JSON array: ["HIV","DM","SLE",null]
    medications TEXT,             -- current regular medications
    allergies TEXT                -- drug allergies
);

CREATE TABLE IF NOT EXISTS chief_complaints (
    id INTEGER PRIMARY KEY,
    hadm_id TEXT REFERENCES patients(hadm_id),
    chief_complaint TEXT,         -- 主诉原文
    symptom_onset TEXT,           -- 发病时间描述
    symptom_duration_days INTEGER,
    symptom_evolution TEXT        -- 症状演变
);

CREATE TABLE IF NOT EXISTS oral_examinations (
    id INTEGER PRIMARY KEY,
    hadm_id TEXT REFERENCES patients(hadm_id),
    lesion_location TEXT,         -- 部位：buccal_mucosa/lip/tongue/palate/gingiva/floor_of_mouth
    lesion_morphology TEXT,       -- 形态：plaque/erosion/ulcer/vesicle/bulla/reticular/atrophic/macule
    lesion_size_mm TEXT,          -- 大小范围
    lesion_color TEXT,
    lesion_texture TEXT,
    nikolsky_sign TEXT,           -- positive/negative/not_tested
    extraoral_findings TEXT,      -- 口腔外体征：skin_lesions/eye_lesions/genital_lesions/none
    oral_hygiene TEXT,            -- good/fair/poor
    additional_notes TEXT
);

CREATE TABLE IF NOT EXISTS lab_results (
    id INTEGER PRIMARY KEY,
    hadm_id TEXT REFERENCES patients(hadm_id),
    cbc_wbc REAL,                 -- 白细胞 (×10⁹/L)
    cbc_hb REAL,                  -- 血红蛋白 (g/L)
    cbc_plt REAL,                 -- 血小板 (×10⁹/L)
    esr REAL,                     -- 血沉 (mm/h)
    crp REAL,                     -- C反应蛋白 (mg/L)
    ana TEXT,                     -- ANA：positive/negative/nucleolar/speckled
    anti_dsdna REAL,              -- 抗dsDNA (IU/mL)
    anti_desmoglein1 REAL,        -- 抗桥粒芯蛋白1 (U/mL)
    anti_desmoglein3 REAL,        -- 抗桥粒芯蛋白3 (U/mL)
    anti_bp180 REAL,              -- 抗BP180 (U/mL)
    anti_bp230 REAL,              -- 抗BP230 (U/mL)
    hiv_test TEXT,                -- positive/negative
    hba1c REAL,                   -- 糖化血红蛋白 (%)
    serum_iron REAL,              -- 血清铁 (μmol/L)
    serum_folate REAL,            -- 叶酸 (nmol/L)
    serum_b12 REAL,               -- 维生素B12 (pmol/L)
    tspot TEXT                    -- T-SPOT：positive/negative
);

CREATE TABLE IF NOT EXISTS microbiology_results (
    id INTEGER PRIMARY KEY,
    hadm_id TEXT REFERENCES patients(hadm_id),
    fungal_smear TEXT,            -- 真菌涂片：positive/negative
    fungal_culture TEXT,          -- 真菌培养及菌种鉴定
    hsv_pcr TEXT,                 -- HSV-1/2 PCR：positive/negative
    vzv_pcr TEXT,                 -- VZV PCR：positive/negative
    cmv_pcr TEXT,                 -- CMV PCR：positive/negative
    bacterial_culture TEXT,       -- 细菌培养+药敏
    hp_test TEXT                  -- HP检测：positive/negative
);

CREATE TABLE IF NOT EXISTS pathology_results (
    id INTEGER PRIMARY KEY,
    hadm_id TEXT REFERENCES patients(hadm_id),
    biopsy_site TEXT,             -- 活检部位
    he_findings TEXT,             -- HE染色镜下所见
    dif_findings TEXT,            -- 直接免疫荧光 (DIF)
    iif_findings TEXT,            -- 间接免疫荧光 (IIF)
    pathological_diagnosis TEXT   -- 病理诊断
);

CREATE TABLE IF NOT EXISTS diagnoses (
    id INTEGER PRIMARY KEY,
    hadm_id TEXT REFERENCES patients(hadm_id),
    primary_diagnosis TEXT,       -- 主要诊断
    differential_diagnoses TEXT,  -- JSON array of 鉴别诊断
    icd11_code TEXT,
    diagnosis_category TEXT,      -- 诊断类别枚举
    diagnosis_basis TEXT          -- 诊断依据 (JSON)
);

CREATE TABLE IF NOT EXISTS treatments (
    id INTEGER PRIMARY KEY,
    hadm_id TEXT REFERENCES patients(hadm_id),
    topical_treatment TEXT,       -- 局部治疗 (JSON)
    systemic_treatment TEXT,      -- 全身治疗 (JSON)
    adjunctive_treatment TEXT,    -- 辅助治疗 (JSON)
    follow_up_plan TEXT,          -- 随访计划
    admission_needed TEXT,        -- 是否需要住院：yes/no
    prognosis TEXT                -- 预后
);
CREATE TABLE IF NOT EXISTS tcm_four_diagnosis (
    id INTEGER PRIMARY KEY,
    hadm_id TEXT REFERENCES patients(hadm_id),
    wang_diagnosis TEXT,           -- 望诊：病损形态+舌象+面色+神态
    wen_diagnosis TEXT,            -- 闻诊：口臭+声音+善太息
    wen_inquiry TEXT,              -- 问诊：寒热/汗出/疼痛性质/口干/口味/情志/饮食/二便/睡眠/月经
    qie_diagnosis TEXT,            -- 切诊：脉象描述
    tongue_body TEXT,              -- 舌质：淡红/红/暗红/紫暗/淡胖/红绛
    tongue_coating TEXT,           -- 舌苔：薄白/薄黄/黄腻/白腻/少苔/无苔/剥苔
    tongue_vein TEXT,              -- 舌下络脉：正常/迂曲怒张/紫暗
    pulse_description TEXT          -- 脉象总结：弦/滑/数/细/涩/濡/弱/沉/浮
);

CREATE TABLE IF NOT EXISTS tcm_diagnoses (
    id INTEGER PRIMARY KEY,
    hadm_id TEXT REFERENCES patients(hadm_id),
    tcm_disease_name TEXT,         -- 中医病名：口癣/口疮/鹅口疮/舌痛症/唇风/猫眼疮/火赤疮/口痹/燥证
    syndrome_differentiation TEXT, -- 辨证分型
    syndrome_basis TEXT,           -- 辨证依据
    treatment_principle TEXT       -- 治则治法
);

CREATE TABLE IF NOT EXISTS tcm_prescriptions (
    id INTEGER PRIMARY KEY,
    hadm_id TEXT REFERENCES patients(hadm_id),
    formula_name TEXT,             -- 方剂名称
    formula_composition TEXT,      -- 组成：JSON [{herb, dosage_g, special_preparation}]
    preparation_method TEXT,       -- 煎服法
    modifications TEXT,            -- 临证加减：JSON [{condition, modification}]
    patent_medicines TEXT,          -- 中成药配合：JSON [{name, dosage, frequency}]
    external_treatment TEXT,       -- 中医外治：含漱/外敷/针灸/耳穴
    acupuncture_points TEXT        -- 针灸选穴
);
"""

# ── 12 例口腔黏膜病典型病例 ────────────────────────
SAMPLE_CASES = [
    {
        "hadm_id": "OLP001",
        "patient": (45, "F", '["none"]', "无", "无"),
        "chief_complaint": (
            "双侧颊黏膜白色条纹伴糜烂3月余，进食辛辣食物时灼痛加剧",
            "3月前无明显诱因出现双侧颊黏膜不适",
            90,
            "最初为白色网状条纹，无自觉症状。1月前开始在白色条纹基础上出现糜烂面，进食刺激性食物时疼痛明显。近2周右侧颊部糜烂面扩大。"
        ),
        "oral_exam": (
            "bilateral_buccal_mucosa,tongue_lateral",
            "reticular,erosion",
            "reticular: 2-3cm; erosion: 0.8x1.2cm (right buccal)",
            "white_reticular_striae; erythematous_erosion_with_yellow_pseudomembrane",
            "smooth_striae; friable_erosion_base",
            "negative",
            "none",
            "fair",
            "Wickham纹可见于双侧颊黏膜。右侧糜烂面边缘可见放射状白色条纹。舌侧缘可见类似白色网状病变。"
        ),
        "lab": (7.2, 135, 280, 22, 5.0, "negative", None, None, None, None, None, "negative", None, None, None, None, "negative"),
        "micro": ("negative", None, "negative", None, None, None, None),
        "pathology": (
            "right_buccal_mucosa",
            "鳞状上皮不规则增生，基底细胞液化变性，上皮下带状淋巴细胞浸润带，胶样小体可见",
            "纤维蛋白原沿基底膜带线状沉积，IgM阳性",
            None,
            "符合口腔扁平苔藓"
        ),
        "diagnosis": (
            "糜烂型口腔扁平苔藓 (Erosive Oral Lichen Planus)",
            '["慢性盘状红斑狼疮","苔藓样反应","白斑"]',
            "DA01.1",
            "oral_lichen_planus",
            '{"clinical":"Wickham纹+糜烂，双侧对称","pathology":"基底细胞液化变性+带状淋巴细胞浸润","DIF":"纤维蛋白原沿BMZ沉积"}'
        ),
        "treatment": (
            '{"triamcinolone_acetonide_0.1pct_ointment":"tid topical"}',
            '{"prednisolone":"20mg qd po for 2w then taper","hydroxychloroquine":"200mg bid po if resistant"}',
            '{"oral_hygiene_instruction":"yes","avoid_spicy_food":"yes","stress_management":"yes"}',
            "2周后复诊，评估糜烂愈合情况；若4周无效考虑羟氯喹",
            "no",
            "慢性病程，可控制但难以根治。约1%恶变风险需每年随访"
        ),
    },
    {
        "hadm_id": "PV001",
        "patient": (52, "M", '["none"]', "无", "青霉素"),
        "chief_complaint": (
            "口腔多发糜烂疼痛2月，进食困难伴体重下降5kg",
            "2月前无明显诱因出现口腔内多处水疱，疱壁薄易破",
            60,
            "初期为口腔内散在水疱，数小时即破溃形成糜烂面。糜烂逐渐扩大融合，2周前开始出现进食困难。外院按'口腔溃疡'治疗无效。"
        ),
        "oral_exam": (
            "bilateral_buccal_mucosa,palate_soft,gingiva,ventral_tongue",
            "erosion,ulcer,desquamative_gingivitis",
            "多处糜烂面，最大约3x2cm (软腭)",
            "bright_red_erosion_with_fibrinous_exudate",
            "friable; tender_to_palpation",
            "positive",
            "skin_crusts_on_scalp_and_chest",
            "poor",
            "Nikolsky 征阳性——轻压正常黏膜即可揭起上皮。剥脱性龈炎明显。头皮和胸背部可见松弛性水疱及结痂。"
        ),
        "lab": (10.5, 118, 350, 45, 18.0, "negative", None, 15.0, 185.0, None, None, "negative", None, None, None, None, "negative"),
        "micro": ("negative", None, "negative", None, None, None, None),
        "pathology": (
            "right_buccal_mucosa_perilesional",
            "表皮内水疱，棘层松解细胞(Tzanck细胞)可见，基底细胞呈'墓碑状'排列于真皮乳头上",
            "IgG和C3沿棘细胞间网状沉积 (鱼网状)",
            "抗Dsg1: 185 U/mL; 抗Dsg3: 230 U/mL",
            "符合寻常型天疱疮"
        ),
        "diagnosis": (
            "寻常型天疱疮 (Pemphigus Vulgaris)",
            '["瘢痕性类天疱疮","大疱性类天疱疮","多形红斑"]',
            "EB40.0",
            "pemphigus_vulgaris",
            '{"clinical":"松弛性水疱+Nikolsky征阳性+口腔+皮肤累及","pathology":"棘层松解+墓碑状基底细胞","DIF":"IgG/C3棘细胞间网状沉积","serology":"抗Dsg1/Dsg3阳性"}'
        ),
        "treatment": (
            '{"triamcinolone_acetonide_0.1pct_ointment":"tid topical","chlorhexidine_mouthwash":"bid"}',
            '{"prednisolone":"1mg/kg/d (60mg) po","mycophenolate_mofetil":"1g bid po as steroid_sparing"}',
            '{"calcium_vitaminD":"yes","gastric_protection":"omeprazole 20mg qd","nutritional_support":"yes"}',
            "2周复诊减激素；每月监测血常规、肝肾功能、血糖、血压",
            "yes",
            "需住院控制急性期。规范治疗预后良好，需长期免疫抑制维持"
        ),
    },
    {
        "hadm_id": "OC001",
        "patient": (68, "F", '["type2_diabetes","hypertension"]', "二甲双胍 500mg tid; 硝苯地平 30mg qd", "无"),
        "chief_complaint": (
            "口腔内白色斑块伴灼痛感1周",
            "1周前感冒发热后口服头孢类抗生素5天，随后出现口腔不适",
            7,
            "服药第4天开始感觉口腔内黏膜不适，随后出现白色斑块，可擦去，擦后留下红色糜烂面。口干感明显。"
        ),
        "oral_exam": (
            "palate_hard,palate_soft,bilateral_buccal_mucosa,dorsal_tongue",
            "pseudomembrane,plaque,erosion_mild",
            "弥漫性，覆盖硬软腭及颊黏膜约70%面积",
            "creamy_white_pseudomembrane; erythematous_base_when_scraped",
            "curd_like_plaques_easily_scraped_off",
            "not_tested",
            "angular_cheilitis_bilateral",
            "fair",
            "白色凝乳状假膜，可用压舌板刮除，刮后基底充血但无明显出血。双侧口角可见皲裂及白色分泌物。舌背可见白色斑块。"
        ),
        "lab": (9.2, 128, 250, 35, 15.0, None, None, None, None, None, None, "negative", 8.2, None, None, None, "negative"),
        "micro": ("positive", "Candida albicans +++", "negative", None, None, None, None),
        "pathology": (
            "palate",
            "上皮表层可见大量真菌菌丝和孢子(PAS染色阳性)，上皮下炎症细胞浸润",
            None,
            None,
            "符合口腔念珠菌病（假膜型）"
        ),
        "diagnosis": (
            "急性假膜型口腔念珠菌病 (Acute Pseudomembranous Oral Candidiasis)",
            '["白色海绵状斑痣","口腔毛状白斑","化学灼伤"]',
            "1F23.0",
            "oral_candidiasis",
            '{"clinical":"可擦除白色假膜+抗生素使用史+糖尿病","microbiology":"真菌涂片阳性+Candida albicans培养","host_factors":"糖尿病未控制+HbA1c 8.2%"}'
        ),
        "treatment": (
            '{"nystatin_oral_suspension":"100000U qid swish_and_swallow 7d","miconazole_gel":"qid topical"}',
            '{"fluconazole":"200mg qd po day1 then 100mg qd 7d if refractory"}',
            '{"glycemic_control":"内分泌科会诊","denture_hygiene":"义齿清洁指导","probiotics":"建议补充"}',
            "1周后复诊评估；复查空腹血糖及HbA1c",
            "no",
            "预后良好。需控制血糖预防复发。如反复发作考虑预防性抗真菌"
        ),
    },
    {
        "hadm_id": "RAS001",
        "patient": (24, "F", '["none"]', "无", "无"),
        "chief_complaint": (
            "反复口腔溃疡3年，近1月发作频繁",
            "3年前开始反复发作口腔溃疡，约每月1-2次",
            30,
            "每次发作持续10-14天自愈。发作部位不固定，每次1-3个。1月前工作压力增大后发作频率增加至每周都有新发溃疡。父母有类似病史。"
        ),
        "oral_exam": (
            "lower_labial_mucosa,ventral_tongue,lateral_tongue",
            "ulcer_round_oval,well_circumscribed",
            "0.3-0.8cm直径，3个独立溃疡",
            "yellowish_gray_pseudomembrane_with_erythematous_halo",
            "smooth_base; tender",
            "not_tested",
            "none",
            "good",
            "溃疡呈圆形/椭圆形，边界清晰，周围有红晕。位于非角化黏膜。触痛明显。无瘢痕形成。"
        ),
        "lab": (6.5, 130, 300, 10, 2.0, None, None, None, None, None, None, None, None, 8.5, 9.0, 180, None),
        "micro": ("negative", None, "negative", None, None, None, None),
        "pathology": (
            None, None, None, None, None
        ),
        "diagnosis": (
            "复发性阿弗他口炎（轻型）(Recurrent Aphthous Stomatitis, Minor)",
            '["白塞病","疱疹性口炎","创伤性溃疡"]',
            "DA01.1",
            "recurrent_aphthous",
            '{"clinical":"反复发作+非角化黏膜+圆形溃疡+家族史","lab":"无特异性异常","exclusion":"无生殖器溃疡/眼炎/皮肤病变排除白塞病"}'
        ),
        "treatment": (
            '{"triamcinolone_acetonide_0.1pct_in_orabase":"tid apply to ulcers","benzydamine_hcl_mouthwash":"qid"}',
            '{"colchicine":"0.5mg bid po if frequent recurrence","zinc_sulfate":"50mg qd po"}',
            '{"trigger_avoidance":"stress_management, avoid SLS toothpaste","nutritional_supplement":"B12+folate 酌情"}',
            "若1月内无明显改善复诊。考虑排除白塞病行眼科/皮肤科会诊",
            "no",
            "预后良好。随年龄增长发作频率可能降低"
        ),
    },
    {
        "hadm_id": "HSV001",
        "patient": (7, "M", '["none"]', "无", "无"),
        "chief_complaint": (
            "发热后口唇及口腔内多发小水疱3天，疼痛拒食",
            "3天前发热39°C，1天后出现口唇周围水疱",
            3,
            "发热后迅速出现口唇和口腔内成簇小水疱。疼痛明显，患儿拒食拒饮水。既往无类似发作史（初次感染）。同班同学有类似症状。"
        ),
        "oral_exam": (
            "vermilion_border,perioral_skin,gingiva,palate_hard,tongue_dorsal",
            "vesicle_clustered,erosion,ulcer",
            "成簇小水疱1-3mm，部分已破溃融合成不规则糜烂",
            "clear_vesicles_on_erythematous_base; yellowish_crusts_on_lip",
            "friable; painful",
            "not_tested",
            "perioral_vesicles_and_crusts",
            "fair",
            "唇红缘及口周皮肤可见成簇小水疱，部分已破溃结痂。口腔内牙龈、硬腭散在水疱及糜烂。龈缘红肿明显（疱疹性龈口炎表现）。"
        ),
        "lab": (8.0, 140, 260, 20, 8.0, None, None, None, None, None, None, None, None, None, None, None, None),
        "micro": (None, None, "positive_HSV1", None, None, None, None),
        "pathology": (None, None, None, None, None),
        "diagnosis": (
            "原发性疱疹性龈口炎 (Primary Herpetic Gingivostomatitis)",
            '["疱疹性咽峡炎","手足口病","多形红斑"]',
            "1F00.0",
            "herpes_simplex",
            '{"clinical":"发热后成簇小水疱+龈口炎+初次感染","epidemiology":"同班同学类似症状","microbiology":"HSV-1 PCR阳性"}'
        ),
        "treatment": (
            '{"lidocaine_viscous_2pct":"apply before meals for pain control","chlorhexidine_gel_0.2pct":"bid topical"}',
            '{"acyclovir":"15mg/kg 5x/d po for 7d (early within 72h)","acetaminophen":"15mg/kg q6h prn for fever"}',
            '{"hydration":"鼓励饮水和软食，防止脱水","isolation":"避免密切接触其他儿童至结痂"}',
            "若72小时内无改善或进食困难加重考虑住院补液。5天后复诊",
            "no",
            "初次感染后HSV潜伏于三叉神经节，可能在免疫力降低时复发为唇疱疹"
        ),
    },
    {
        "hadm_id": "DLE001",
        "patient": (38, "F", '["none"]', "无", "无"),
        "chief_complaint": (
            "下唇及颊黏膜白色斑块伴萎缩半年",
            "半年前发现下唇有'白斑'，逐渐扩大",
            180,
            "最初为下唇红色斑片，逐渐出现白色条纹和萎缩。无明显疼痛。日晒后加重。曾在外院诊断为'扁平苔藓'，用药无效。无系统性疾病史但偶有面部红斑。"
        ),
        "oral_exam": (
            "lower_lip_vermilion,bilateral_buccal_mucosa",
            "plaque_atrophic,erosion_mild,reticular_striae_radiating",
            "下唇约2cm区域；双侧颊黏膜散在",
            "white_radiating_striae_with_central_atrophic_erythema",
            "atrophic_center; radial_white_striae_at_periphery; telangiectasia",
            "not_tested",
            "malar_erythema_mild",
            "good",
            "下唇病变呈特征性'三区模式'：中央萎缩性红斑，周围放射状白色条纹，边缘毛细血管扩张。颊部可见淡红斑。"
        ),
        "lab": (5.0, 120, 200, 30, 4.0, "positive_speckled_1:320", 45.0, None, None, None, None, "negative", None, None, None, None, "negative"),
        "micro": ("negative", None, "negative", None, None, None, None),
        "pathology": (
            "lower_lip",
            "表皮萎缩，基底细胞液化变性，真皮浅层及深层血管周围淋巴细胞浸润，PAS染色示基底膜增厚",
            "IgG、IgM、C3沿基底膜带颗粒状沉积",
            None,
            "符合盘状红斑狼疮"
        ),
        "diagnosis": (
            "口腔盘状红斑狼疮 (Oral Discoid Lupus Erythematosus)",
            '["口腔扁平苔藓","系统性红斑狼疮口腔表现","光化性唇炎"]',
            "4A40.0",
            "discoid_lupus",
            '{"clinical":"放射状白纹+中央萎缩+毛细血管扩张(三区模式)+日晒加重+唇部好发","pathology":"基底细胞液化+真皮深浅层血管周淋巴细胞浸润+PAS基底膜增厚","DIF":"IgG/IgM/C3沿BMZ颗粒状沉积","serology":"ANA 1:320+抗dsDNA升高"}'
        ),
        "treatment": (
            '{"sunscreen_SPF50":"q2h to lips and face","triamcinolone_acetonide_0.1pct_ointment":"bid to lip lesion"}',
            '{"hydroxychloroquine":"200mg bid po (baseline eye exam required)","prednisolone":"10mg qd po short_course_if_flare"}',
            '{"sun_protection":"宽檐帽+避免10-16点日晒","smoking_cessation":"劝导戒烟"}',
            "1月后复诊；羟氯喹前需眼科检查(基线)；每6-12月眼科随访",
            "no",
            "盘状红斑狼疮约5-10%可进展为系统性红斑狼疮，需长期随访"
        ),
    },
    {
        "hadm_id": "LEUK001",
        "patient": (58, "M", '["smoking_30pack_years","alcohol_heavy"]', "无", "无"),
        "chief_complaint": (
            "口腔内右侧颊黏膜白色斑块半年，无法擦除",
            "半年前偶然发现右侧颊黏膜白色斑块，无明显不适",
            180,
            "斑块缓慢增大。近1月出现轻微粗糙感。吸烟30年，每日1包；饮白酒30年，每日约150ml。"
        ),
        "oral_exam": (
            "right_buccal_mucosa,right_retromolar_area",
            "plaque_homogeneous_white",
            "2.5x1.5cm",
            "uniform_opaque_white; non_scrapable",
            "slightly_rough_surface; firm_to_palpation",
            "not_tested",
            "nicotine_staining_on_teeth",
            "poor",
            "白色均质斑块，边界清晰但不规则。不能擦除。触诊较周围正常黏膜稍硬。无明显溃疡或疣状增生。舌侧缘及口底未见类似病变。"
        ),
        "lab": (7.0, 145, 220, 12, 3.0, None, None, None, None, None, None, None, None, None, None, None, None),
        "micro": ("negative", None, "negative", None, None, None, None),
        "pathology": (
            "right_buccal_mucosa",
            "鳞状上皮增生伴过度角化（正角化），棘层肥厚，上皮脚延长。上皮无异型增生。上皮下轻度慢性炎细胞浸润。",
            None,
            None,
            "口腔白斑，无异型增生（低风险）"
        ),
        "diagnosis": (
            "口腔白斑（均质型，无异型增生）(Oral Leukoplakia, Homogeneous, No Dysplasia)",
            '["摩擦性角化","口腔扁平苔藓(斑块型)","白色海绵状斑痣","增殖性疣状白斑"]',
            "DA01.0",
            "leukoplakia",
            '{"clinical":"不可擦除的均质白色斑块+吸烟饮酒危险因素","pathology":"过度角化+棘层肥厚，无异型增生(关键)","site":"右颊-高危非均质型需排除"}'
        ),
        "treatment": (
            '{"none":"topical treatment not indicated for homogeneous leukoplakia without dysplasia"}',
            '{"retinoids":"not routinely recommended for low_risk"}',
            '{"smoking_cessation":"强烈建议戒烟","alcohol_reduction":"强烈建议减少饮酒","regular_followup":"每6月口腔科随访"}',
            "强烈建议戒烟戒酒。每6月随访口腔检查；如出现疼痛/增大/溃疡/颜色改变随时就诊",
            "no",
            "无异型增生的均质型白斑恶变风险相对较低(<5%)，但需要终身随访。关键是戒烟戒酒+定期复查"
        ),
    },
    {
        "hadm_id": "EM001",
        "patient": (28, "M", '["none"]', "无", "磺胺类药物"),
        "chief_complaint": (
            "口腔及口唇广泛糜烂出血性结痂3天，发热38.5°C",
            "5天前感冒口服复方新诺明，2天后开始出现口腔不适",
            3,
            "服药后约48小时出现口唇肿胀、水疱，迅速发展为广泛糜烂和出血性结痂。口腔内疼痛剧烈，进食困难。同时出现双手背和躯干散在靶形红斑。"
        ),
        "oral_exam": (
            "lips_diffuse,buccal_mucosa_diffuse,tongue,palate",
            "erosion_extensive,crust_hemorrhagic,erythema_multiforme_target_lesions",
            "弥漫性累及口唇,颊黏膜,舌背,软腭",
            "hemorrhagic_crust_on_lips; diffuse_erythematous_erosions_intraoral",
            "friable; severely_tender; bleeding_on_contact",
            "negative",
            "target_lesions_on_hands_and_forearms; scattered_on_trunk",
            "fair",
            "口唇肿胀明显伴厚层出血性血痂——特征性表现。口腔内弥漫性糜烂和假膜。双手背和躯干散在典型'靶形红斑'(同心圆三层: 中心暗红/水疱-中间苍白水肿-外围红斑)。"
        ),
        "lab": (11.0, 140, 300, 45, 30.0, None, None, None, None, None, None, "negative", None, None, None, None, "negative"),
        "micro": ("negative", None, "negative", None, None, None, None),
        "pathology": (
            "left_buccal_mucosa",
            "表皮内及表皮下分离，角质形成细胞坏死(凋亡)，真皮浅层水肿，血管周围淋巴细胞浸润，界面性皮炎改变",
            "非特异性",
            None,
            "符合多形红斑"
        ),
        "diagnosis": (
            "多形红斑（重型/口腔为主型）(Erythema Multiforme, Major)",
            '["Stevens-Johnson综合征","寻常型天疱疮","疱疹性口炎","固定性药疹"]',
            "EB12",
            "erythema_multiforme",
            '{"clinical":"药物诱因(磺胺)+靶形红斑+口唇出血性结痂+皮肤累及","pathology":"界面性皮炎+角质形成细胞坏死","distribution":"口腔+口唇+手背+躯干"}'
        ),
        "treatment": (
            '{"lidocaine_viscous_2pct":"qid before meals","chlorhexidine_mouthwash_0.12pct":"bid","triamcinolone_0.1pct_ointment":"bid to lip lesions"}',
            '{"prednisolone":"0.5mg/kg/d (30mg) po for 7-10d taper","acyclovir":"400mg 5x/d po for 7d (if HSV trigger suspected)"}',
            '{"hydration":"积极补液防止脱水","pain_management":"必要时镇痛","drug_avoidance":"永久避免磺胺类药物"}',
            "每日随访至急性期控制。告之患者永久禁用磺胺类药物及复方新诺明",
            "yes",
            "多数预后良好，2-4周恢复。需排除SJS（如有皮肤剥脱面积>10%或黏膜严重累及+系统症状）。复发可能与HSV再激活相关"
        ),
    },
    {
        "hadm_id": "ANUG001",
        "patient": (22, "M", '["none"]', "无", "无"),
        "chief_complaint": (
            "牙龈剧痛伴自发出血、口腔恶臭5天",
            "期末考试期间熬夜1周，饮食不规律，口腔卫生忽略",
            5,
            "牙龈突然出现剧烈疼痛、自发性出血。口腔内有明显金属味和恶臭。发热38°C，全身乏力。近1年未洁牙，吸烟10支/日×3年。"
        ),
        "oral_exam": (
            "interdental_papillae_mandibular_anterior,interdental_papillae_maxillary_anterior",
            "necrosis_punched_out_papillae,ulcer,hemorrhage,pseudomembrane_grayish",
            "下颌前牙区和上颌前牙区龈乳头坏死",
            "grayish_pseudomembrane_over_necrotic_papillae; erythematous_margins",
            "necrotic_crater_like_papillae; fetid_odor_characteristic; bleed_on_touch",
            "not_tested",
            "submandibular_lymphadenopathy_tender",
            "poor",
            "龈乳头呈'火山口'状坏死缺损，表面覆盖灰白色假膜。去除假膜后易出血——特征表现。明显腐败性口臭。颌下淋巴结肿大压痛。"
        ),
        "lab": (12.0, 140, 280, 40, 25.0, None, None, None, None, None, None, "negative", None, None, None, None, None),
        "micro": ("negative", None, "negative", None, None, "Fusobacterium+Prevotella+Spirochetes (mixed anaerobic)", None),
        "pathology": (None, None, None, None, None),
        "diagnosis": (
            "急性坏死性溃疡性龈炎 (Acute Necrotizing Ulcerative Gingivitis, ANUG)",
            '["疱疹性龈口炎","急性白血病牙龈表现","坏死性牙周炎"]',
            "DA0C.0",
            "anug",
            '{"clinical":"龈乳头火山口状坏死+腐败性口臭+自发出血+应激/熬夜诱因+年轻男性+吸烟","lab":"白细胞升高+CRP升高","microbiology":"混合厌氧菌感染(梭杆菌+普雷沃菌+螺旋体)","exclusion":"需排除急性白血病"}'
        ),
        "treatment": (
            '{"chlorhexidine_0.12pct_mouthwash":"bid for 7d","hydrogen_peroxide_3pct":"diluted 1:1 rinse tid for 3d"}',
            '{"metronidazole":"400mg tid po for 7d","acetaminophen":"500mg q6h prn pain","amoxicillin":"500mg tid po for 7d if severe/systemic"}',
            '{"debridement":"gentle ultrasonic debridement after acute phase","oral_hygiene_instruction":"ohi","smoking_cessation":"强烈劝导戒烟","stress_management":"规律作息"}',
            "3天后复诊清创；1周后复诊评估愈合。排除HIV/AIDS",
            "no",
            "及时治疗预后良好，坏死龈乳头2-3周愈合。需排除HIV/AIDS。戒烟和口腔卫生维护是关键"
        ),
    },
    {
        "hadm_id": "LR001",
        "patient": (55, "F", '["hypertension"]', "氨氯地平 5mg qd（新近更换，2月前由依那普利改为氨氯地平）", "无"),
        "chief_complaint": (
            "双侧颊黏膜白色条纹伴糜烂3月，更换降压药后约1月开始出现",
            "2月前因高血压换用氨氯地平，约1月后开始出现口腔不适",
            60,
            "最初为双侧颊黏膜烧灼感，随后出现白色条纹和糜烂。病变局限于与双侧颊黏膜咬合线附近。停用氨氯地平2周后，症状有所减轻。"
        ),
        "oral_exam": (
            "bilateral_buccal_mucosa_along_occlusal_line",
            "reticular_striae,erosion_linear,ulcer_small",
            "沿咬合线分布，约2×4cm，双侧对称",
            "white_reticular_striae; linear_erosions_at_occlusal_line",
            "smooth_reticular; erosions_along_mechanical_stress_line",
            "negative",
            "none",
            "fair",
            "病变严格沿咬合线分布，呈线状而非放射状。Wickham纹不如经典OLP明显。双侧对称。最近的服药史（氨氯地平）可疑。"
        ),
        "lab": (6.5, 132, 260, 10, 2.5, "negative", None, None, None, None, None, None, None, None, None, None, None),
        "micro": ("negative", None, None, None, None, None, None),
        "pathology": (
            "right_buccal_mucosa",
            "界面性皮炎，基底细胞液化变性，上皮下带状淋巴细胞浸润。可见散在嗜酸性粒细胞及浆细胞浸润（与经典OLP不同）。",
            "纤维蛋白原沿BMZ线状沉积（非特异性）",
            None,
            "符合苔藓样反应，倾向于药物相关性"
        ),
        "diagnosis": (
            "苔藓样反应（氨氯地平相关）(Oral Lichenoid Reaction, Amlodipine-induced)",
            '["口腔扁平苔藓","移植物抗宿主病口腔表现","接触性过敏反应"]',
            "DA01.1",
            "lichenoid_reaction",
            '{"clinical":"沿咬合线分布+换药时间关联+停用后改善+双侧对称","pathology":"嗜酸性粒细胞+浆细胞浸润（不同于OLP）","drug_history":"氨氯地平2月前新近更换","de_challenge":"停药2周部分缓解（阳性去激发反应）"}'
        ),
        "treatment": (
            '{"triamcinolone_acetonide_0.1pct_in_orabase":"bid to erosive areas"}',
            '{"switch_amlodipine_to_losartan":"心内科会诊更换降压药"}',
            '{"avoid_mechanical_irritation":"避免咬颊习惯","dental_restoration_check":"检查牙科修复体是否适合"}',
            "更换降压药后2-4周随访观察；完全停用氨氯地平后8周评估",
            "no",
            "去除致病药物后预后良好，通常6-8周内完全消退。需心内科协作更换降压药"
        ),
    },
    {
        "hadm_id": "ATOLP001",
        "patient": (62, "M", '["type2_diabetes","hypertension"]', "二甲双胍 500mg bid; 氨氯地平 5mg qd", "无"),
        "chief_complaint": (
            "口腔内红色斑块伴灼痛感6月",
            "6月前发现口腔内红色区域，逐渐扩大伴烧灼感",
            180,
            "病变缓慢进展，主要是烧灼痛和干燥感。进食辛辣食物时明显。无明显溃疡或水疱。已尝试多种漱口水无效。"
        ),
        "oral_exam": (
            "bilateral_buccal_mucosa_diffuse,ventral_tongue",
            "atrophic_erythematous_diffuse,erosion_superficial",
            "弥漫性累及颊黏膜大部及舌腹",
            "diffuse_bright_erythema; scattered_white_reticular_striae_subtle",
            "smooth_atrophic; friable_superficial_erosions",
            "negative",
            "none",
            "fair",
            "弥漫性萎缩性红斑区域与散在的细微白色网状条纹混合存在。无明确糜烂面——主要是萎缩性改变。舌腹轻度萎缩。"
        ),
        "lab": (6.0, 130, 270, 15, 3.0, "negative", None, None, None, None, None, "negative", 7.8, None, None, None, "negative"),
        "micro": ("negative", "轻度 Candida 生长", None, None, None, None, None),
        "pathology": (
            "right_buccal_mucosa",
            "上皮萎缩变薄，基底细胞液化变性，上皮下致密带状淋巴细胞浸润，可见胶样小体",
            "纤维蛋白原沿基底膜带线状沉积",
            None,
            "符合萎缩型口腔扁平苔藓，伴轻度念珠菌定植"
        ),
        "diagnosis": (
            "萎缩型口腔扁平苔藓伴念珠菌定植 (Atrophic Oral Lichen Planus with Candida Colonization)",
            '["口腔念珠菌病(萎缩型)","干燥综合征口腔表现","缺铁性吞咽困难(Plummer-Vinson)","慢性移植物抗宿主病"]',
            "DA01.1",
            "oral_lichen_planus",
            '{"clinical":"弥漫性萎缩性红斑+散在白纹+烧灼感","pathology":"上皮萎缩+基底细胞液化+带状淋巴细胞浸润","microbiology":"轻度念珠菌——可能是继发性定植而非原发性感染"}'
        ),
        "treatment": (
            '{"triamcinolone_acetonide_0.1pct_ointment":"bid to erythematous areas","nystatin_oral_suspension":"100000U qid for 10d"}',
            '{"prednisolone":"15mg qd po for 2w if topical ineffective"}',
            '{"glycemic_control":"内分泌科优化降糖方案","avoid_spicy_acidic_food":"yes","regular_followup":"每3月口腔科随访"}',
            "2周后复诊。若萎缩持续需长期随访排除恶变",
            "no",
            "萎缩型OLP较糜烂型恶变风险略高(约1-3%)，需定期随访排除恶变"
        ),
    },
    {
        "hadm_id": "BP001",
        "patient": (72, "F", '["hypertension","osteoporosis"]', "氨氯地平 5mg qd; 阿仑膦酸钠 70mg qw", "无"),
        "chief_complaint": (
            "口腔内水疱和糜烂反复发作3月，皮肤瘙痒性大疱2月",
            "3月前不明原因出现口腔散在水疱",
            90,
            "口腔水疱持续1-2天破溃形成糜烂。2月前开始出现躯干和四肢皮肤紧张性大疱（疱壁较厚、不易破）。口腔病变较轻，不影响进食。无生殖器累及。无眼部症状。"
        ),
        "oral_exam": (
            "gingiva,bilateral_buccal_mucosa,soft_palate",
            "vesicle_tense,erosion_small,desquamative_gingivitis_mild",
            "散在小水疱及糜烂，最大约1cm",
            "clear_tense_vesicles; superficial_erosions_with_fibrin",
            "tense_vesicle_wall_intact; erosions_clean_base",
            "negative",
            "tense_bullae_on_trunk_and_limbs; urticarial_plaques",
            "fair",
            "口腔内小水疱疱壁较厚(张力性水疱)，与天疱疮的松弛性水疱不同。Nikolsky征阴性——关键鉴别点。皮肤可见紧张性大疱和荨麻疹样斑块。"
        ),
        "lab": (8.0, 125, 280, 30, 10.0, "negative", None, None, 55.0, 120.0, 15.0, None, None, None, None, None, None),
        "micro": ("negative", None, "negative", None, None, None, None),
        "pathology": (
            "left_buccal_mucosa_perilesional",
            "表皮下裂隙及大疱形成。疱腔内可见嗜酸性粒细胞及中性粒细胞。真皮浅层水肿及嗜酸性粒细胞浸润。基底细胞完整(表皮下而非表皮内疱)。",
            "IgG和C3沿基底膜带线状沉积",
            "抗BP180: 120 U/mL (升高); 抗BP230: 15 U/mL (轻度升高)",
            "符合大疱性类天疱疮"
        ),
        "diagnosis": (
            "大疱性类天疱疮（口腔+皮肤累及）(Bullous Pemphigoid, Oral + Cutaneous)",
            '["寻常型天疱疮","瘢痕性类天疱疮","副肿瘤性天疱疮","线状IgA大疱性皮病"]',
            "EB41.0",
            "bullous_pemphigoid",  # Note: not in original enum but should be
            '{"clinical":"张力性水疱+Nikolsky征阴性+皮肤紧张性大疱+口腔轻症+老年","pathology":"表皮下大疱(below BMZ)+嗜酸性粒细胞","DIF":"IgG/C3沿BMZ线状沉积","serology":"抗BP180显著升高(>100U/mL)","differential_from_PV":"表皮下(非表皮内)水疱+Nikolsky(-)+皮肤为主"}'
        ),
        "treatment": (
            '{"triamcinolone_acetonide_0.1pct_ointment":"bid to oral erosions","chlorhexidine_mouthwash_0.12pct":"bid"}',
            '{"prednisolone":"0.5mg/kg/d (30mg) po","doxycycline":"100mg bid po (steroid_sparing_anti_inflammatory)","mycophenolate_mofetil":"if refractory"}',
            '{"osteoporosis_management":"钙剂+维生素D+双膦酸盐优化","gastric_protection":"奥美拉唑 20mg qd","skin_care":"局部激素软膏+伤口护理"}',
            "2周后评估。若水疱控制不佳考虑加用MMF。需排除潜在恶性肿瘤（副肿瘤性天疱疮筛查）",
            "no",
            "预后相对良好，但需要长期免疫抑制治疗。老年患者需注意激素相关不良反应(骨质疏松/糖尿病/感染)。大疱性类天疱疮自限性病程约2-5年"
        ),
    },
]


# ── 中医四诊+辨证+处方数据（按hadm_id索引）────────────
TCM_DATA = {
    "OLP001": {
        "four_diag": (
            "双颊对称性白网纹，基底充血，伴糜烂。舌质暗红，边有瘀点，苔薄黄微腻。面色稍晦暗，表情焦虑。",
            "语声正常，无口臭，偶善太息。",
            "口腔糜烂处灼痛，进食辛辣加重。口干欲饮温水，口微苦。情志抑郁易怒，胸胁时胀。睡眠差，多梦。大便偏干。",
            "脉弦细略涩。",
            "暗红", "薄黄微腻", "正常", "弦细略涩"
        ),
        "tcm_diag": (
            "口癣", "肝郁气滞，兼有血瘀证",
            "情志抑郁、胸胁胀痛、善太息为肝郁气滞；舌暗红瘀点、脉涩为血瘀；糜烂充血、苔黄腻为郁而化热夹湿。肝郁为本，血瘀湿热为标。",
            "疏肝理气，活血化瘀，兼清湿热"
        ),
        "tcm_rx": (
            "丹栀逍遥散合桃红四物汤加减",
            '[{"herb":"柴胡","dosage":"10g"},{"herb":"当归","dosage":"12g"},{"herb":"白芍","dosage":"15g"},{"herb":"白术","dosage":"10g"},{"herb":"茯苓","dosage":"15g"},{"herb":"牡丹皮","dosage":"10g"},{"herb":"炒栀子","dosage":"10g"},{"herb":"薄荷","dosage":"6g","special":"后下"},{"herb":"炙甘草","dosage":"6g"},{"herb":"桃仁","dosage":"10g"},{"herb":"红花","dosage":"6g"},{"herb":"川芎","dosage":"10g"},{"herb":"生地黄","dosage":"15g"},{"herb":"白鲜皮","dosage":"15g"},{"herb":"黄芩","dosage":"10g"},{"herb":"郁金","dosage":"10g"}]',
            "每日1剂，加水浸泡30分钟，武火煮沸后文火煎30分钟，取汁200ml；二煎加水150ml，煎20分钟，取汁150ml。两煎混合，分早晚两次温服。",
            '[{"condition":"糜烂渗出明显、苔黄腻者","mod":"去生地黄，加黄连6g、黄柏10g、生薏苡仁30g"},{"condition":"口干咽燥、舌红少苔者","mod":"去川芎、红花，减柴胡至6g，加沙参15g、麦冬15g、石斛15g"},{"condition":"睡眠极差者","mod":"加酸枣仁30g（打碎）、首乌藤30g、合欢皮15g"},{"condition":"大便干结难解者","mod":"加火麻仁15g、枳壳10g"}]',
            '[{"name":"郁舒颗粒","dosage":"12g","frequency":"bid","route":"冲服"},{"name":"知柏地黄丸","dosage":"8粒","frequency":"tid","note":"若阴虚明显"}]',
            "康复新液10ml含漱3-5分钟，tid。养阴生肌散少许涂敷糜烂面，bid。",
            "合谷、足三里、三阴交、颊车、地仓、太冲（泻法）"
        ),
    },
    "PV001": {
        "four_diag": (
            "牙龈糜烂红赤如'剥脱状'，颊部糜烂边缘向外扩展，水疱壁薄。舌质红，苔黄腻。",
            "轻度口臭。",
            "口腔糜烂灼痛明显，进食加重。口干欲冷饮，口微苦。小便黄，大便偏干。因持续疼痛3月，情志抑郁焦虑。",
            "脉滑数。",
            "红", "黄腻", "正常", "滑数"
        ),
        "tcm_diag": (
            "火赤疮", "湿热毒蕴证（急性活动期）",
            "口腔糜烂范围广、灼痛明显、水疱、口臭、舌红苔黄腻、脉滑数为湿热毒蕴。湿热毒邪蕴结肌肤黏膜，致腠理不固、棘层松解。实证热证。",
            "清热利湿、凉血解毒"
        ),
        "tcm_rx": (
            "龙胆泻肝汤合五味消毒饮加减",
            '[{"herb":"龙胆草","dosage":"10g"},{"herb":"黄芩","dosage":"12g"},{"herb":"炒栀子","dosage":"10g"},{"herb":"泽泻","dosage":"10g"},{"herb":"通草","dosage":"6g"},{"herb":"车前子","dosage":"15g","special":"包煎"},{"herb":"当归","dosage":"10g"},{"herb":"生地黄","dosage":"20g"},{"herb":"柴胡","dosage":"10g"},{"herb":"生甘草","dosage":"10g"},{"herb":"金银花","dosage":"20g"},{"herb":"野菊花","dosage":"15g"},{"herb":"蒲公英","dosage":"30g"},{"herb":"紫花地丁","dosage":"15g"},{"herb":"牡丹皮","dosage":"12g"},{"herb":"赤芍","dosage":"15g"},{"herb":"土茯苓","dosage":"30g"}]',
            "每日1剂，加水浸泡30分钟，武火煮沸后文火煎30分钟，取汁200ml；二煎取汁150ml。两煎混合，分早晚两次温服。",
            '[{"condition":"糜烂渗出特别重者","mod":"加黄柏12g、苦参10g、白鲜皮15g"},{"condition":"大便秘结者","mod":"加生大黄6g（后下），便通即去"},{"condition":"激素治疗后出现阴虚火旺（舌红少苔、口干、五心烦热）","mod":"转为知柏地黄丸合二至丸加减"},{"condition":"激素减量期气阴两虚（乏力、口干、舌淡红少苔）","mod":"转为生脉饮合六味地黄汤加减"}]',
            '[{"name":"雷公藤多苷片","dosage":"20mg","frequency":"tid","note":"激素助减，专科医师监控下使用，注意生殖毒性、肝肾毒性"}]',
            "黄柏15g、苦参15g、马齿苋30g、金银花20g，煎汤300ml，含漱tid-qid。青黛散少许涂糜烂面bid。",
            "合谷、足三里、三阴交、内庭、曲池、血海（泻法）"
        ),
    },
    "OC001": {
        "four_diag": (
            "舌背白膜可擦去，基底发红；腭部弥漫性红斑。舌质红，苔白腻微黄，舌体偏胖边有齿痕。",
            "轻度口臭。",
            "口腔烧灼感午后为重，口干欲饮温水，口中黏腻微甜，纳谷不香，大便偏稀溏，全身困重乏力。",
            "脉滑，右关濡。",
            "红", "白腻微黄", "正常", "滑（右关濡）"
        ),
        "tcm_diag": (
            "鹅口疮", "脾虚湿困，湿热内蕴证",
            "口干不欲多饮、口中黏腻、大便稀溏、舌胖齿痕、脉濡为脾虚湿困；舌红、苔白腻微黄、口臭为湿热内蕴。脾虚为本，湿热为标。",
            "健脾燥湿，清热利湿"
        ),
        "tcm_rx": (
            "参苓白术散合二妙散加减",
            '[{"herb":"党参","dosage":"15g"},{"herb":"白术","dosage":"12g"},{"herb":"茯苓","dosage":"15g"},{"herb":"山药","dosage":"15g"},{"herb":"白扁豆","dosage":"15g"},{"herb":"莲子肉","dosage":"12g"},{"herb":"生薏苡仁","dosage":"30g"},{"herb":"砂仁","dosage":"6g","special":"后下"},{"herb":"桔梗","dosage":"10g"},{"herb":"炙甘草","dosage":"6g"},{"herb":"苍术","dosage":"10g"},{"herb":"黄柏","dosage":"10g"},{"herb":"佩兰","dosage":"10g","special":"后下"},{"herb":"藿香","dosage":"10g","special":"后下"}]',
            "每日1剂，加水浸泡30分钟，武火煮沸后文火煎30分钟，取汁200ml；二煎取汁150ml。两煎混合，分早晚两次温服。",
            '[{"condition":"口干渴明显、苔黄偏重","mod":"加黄芩10g、黄连6g、天花粉15g"},{"condition":"大便稀溏甚、舌淡胖","mod":"加干姜6g、炒白术加量至15g，去黄柏"},{"condition":"纳呆食少明显","mod":"加神曲15g、炒麦芽15g、鸡内金10g"}]',
            '[{"name":"参苓白术丸","dosage":"6g","frequency":"bid","route":"口服"}]',
            "黄连10g、黄柏10g、苦参15g、白鲜皮15g，煎汤200ml，含漱3-5分钟后吐出，bid-tid。青黛散少许涂敷白膜区，bid。",
            "足三里、阴陵泉、丰隆、合谷、内庭（平补平泻）"
        ),
    },
    "RAS001": {
        "four_diag": (
            "溃疡面色红，假膜色黄，周围充血明显。舌质红，舌尖尤红有红点散布，苔薄黄微腻。",
            "轻度口臭。",
            "溃疡灼痛明显，进食及言语时加重。口干欲饮温水，口苦。心烦，失眠多梦。食欲欠佳，大便偏干。",
            "脉滑数，右关尤甚。",
            "红（舌尖红有红点）", "薄黄微腻", "正常", "滑数"
        ),
        "tcm_diag": (
            "口疮", "脾胃湿热，心火上炎证",
            "溃疡红肿灼痛、口苦口臭、苔黄腻、脉滑数为脾胃湿热；舌尖红有红点、心烦失眠为心火上炎。病位在心脾，属实热证。",
            "清热利湿，清心泻火"
        ),
        "tcm_rx": (
            "甘草泻心汤合导赤散加减",
            '[{"herb":"炙甘草","dosage":"12g"},{"herb":"黄芩","dosage":"10g"},{"herb":"黄连","dosage":"6g"},{"herb":"干姜","dosage":"6g"},{"herb":"党参","dosage":"15g"},{"herb":"大枣","dosage":"6枚"},{"herb":"姜半夏","dosage":"9g"},{"herb":"生地黄","dosage":"15g"},{"herb":"淡竹叶","dosage":"10g"},{"herb":"通草","dosage":"6g"},{"herb":"蒲公英","dosage":"15g"},{"herb":"连翘","dosage":"10g"}]',
            "每日1剂，加水浸泡30分钟，武火煮沸后文火煎30分钟，取汁200ml；二煎取汁150ml。两煎混合，分早晚两次温服。",
            '[{"condition":"大便秘结难解","mod":"加生大黄6g（后下）、枳实10g，便通即去大黄"},{"condition":"心烦失眠明显","mod":"加栀子10g、淡豆豉10g，或加莲子心3g"},{"condition":"口黏、苔厚腻","mod":"加藿香10g（后下）、佩兰10g（后下）、生薏苡仁30g"},{"condition":"舌红少津","mod":"酌减黄芩至6g、黄连至3g，加沙参15g、麦冬15g、石斛15g"}]',
            '[{"name":"口炎清颗粒","dosage":"10g","frequency":"bid","route":"冲服"}]',
            "冰硼散少许涂敷溃疡面，bid-tid。",
            "廉泉、颊车、合谷、足三里、三阴交、内庭。耳穴：口、脾、胃、心、神门，王不留行籽贴压。"
        ),
    },
    "HSV001": {
        "four_diag": (
            "口唇成簇小水疱，口内牙龈红肿糜烂。舌质红，苔薄黄。",
            "无特殊。",
            "口唇及口腔灼痛，发热后出现。口干欲饮冷。小便黄。",
            "脉浮数。",
            "红", "薄黄", "正常", "浮数"
        ),
        "tcm_diag": (
            "口疮（疱疹性龈口炎）", "风热外袭，热毒壅盛证",
            "发热后口唇水疱、牙龈红肿、舌红苔黄、脉浮数为风热外袭，热毒壅盛于口。实证热证。",
            "疏风清热，解毒凉血"
        ),
        "tcm_rx": (
            "银翘散合五味消毒饮加减（小儿剂量酌减）",
            '[{"herb":"金银花","dosage":"10g"},{"herb":"连翘","dosage":"10g"},{"herb":"薄荷","dosage":"6g","special":"后下"},{"herb":"牛蒡子","dosage":"10g"},{"herb":"荆芥","dosage":"6g"},{"herb":"淡豆豉","dosage":"10g"},{"herb":"桔梗","dosage":"6g"},{"herb":"生甘草","dosage":"6g"},{"herb":"板蓝根","dosage":"15g"},{"herb":"大青叶","dosage":"10g"}]',
            "每日1剂，加水浸泡20分钟，武火煮沸后文火煎20分钟，取汁150ml；二煎取汁100ml。两煎混合，分3-4次温服（儿童减半）。",
            '[{"condition":"高热不退","mod":"加生石膏20g（先煎）、知母6g"},{"condition":"口腔疼痛剧烈","mod":"加白芷6g、延胡索6g"}]',
            '[{"name":"小儿清热宁颗粒","dosage":"5g","frequency":"tid","route":"冲服"}]',
            "金银花15g、连翘10g、甘草6g，煎汤100ml，含漱tid。",
            "合谷、曲池、大椎、颊车（点刺放血以泄热）"
        ),
    },
    "DLE001": {
        "four_diag": (
            "唇部中央萎缩+放射状白纹+毛细血管扩张+椒盐样色素改变。舌质暗红有散在瘀点，苔薄黄。面色正常（无蝶形红斑）。",
            "语声正常，无口臭。",
            "下唇灼热不适，日晒后加重。口干咽燥，午后偶有面部潮热。月经规律，量偏少，偶夹血块。",
            "脉细涩。",
            "暗红（散在瘀点）", "薄黄", "正常", "细涩"
        ),
        "tcm_diag": (
            "唇风（DLE口腔表现）", "阴虚内热，兼有血瘀证",
            "中央萎缩色红、口干咽燥、午后潮热、脉细数为阴虚内热；放射状白纹、舌瘀点、脉涩、月经夹血块为血瘀。阴虚为本，血瘀为标。",
            "滋阴清热，活血化瘀"
        ),
        "tcm_rx": (
            "知柏地黄丸合桃红四物汤加减",
            '[{"herb":"生地黄","dosage":"20g"},{"herb":"山茱萸","dosage":"12g"},{"herb":"山药","dosage":"15g"},{"herb":"茯苓","dosage":"15g"},{"herb":"牡丹皮","dosage":"10g"},{"herb":"泽泻","dosage":"10g"},{"herb":"知母","dosage":"10g"},{"herb":"黄柏","dosage":"10g"},{"herb":"桃仁","dosage":"10g"},{"herb":"红花","dosage":"6g"},{"herb":"当归","dosage":"12g"},{"herb":"川芎","dosage":"10g"},{"herb":"白芍","dosage":"15g"},{"herb":"丹参","dosage":"15g"},{"herb":"鸡血藤","dosage":"20g"}]',
            "每日1剂，加水浸泡30分钟，武火煮沸后文火煎30分钟，取汁200ml；二煎取汁150ml。两煎混合，分早晚两次温服。",
            '[{"condition":"日晒后加重明显","mod":"加青蒿15g（后下）、地骨皮15g"},{"condition":"口干咽燥明显、舌红少苔","mod":"加沙参15g、麦冬15g、石斛15g"},{"condition":"色素沉着明显","mod":"加白芷10g、白僵蚕10g"}]',
            '[{"name":"知柏地黄丸","dosage":"8粒","frequency":"tid","route":"口服"},{"name":"血府逐瘀口服液","dosage":"10ml","frequency":"bid","route":"口服"}]',
            "青黛散少许涂糜烂面bid。",
            "地仓、颊车、合谷、足三里、三阴交、血海、肾俞"
        ),
    },
    "LEUK001": {
        "four_diag": (
            "右颊白色均质斑块，边界清晰不可擦除。舌质淡暗，苔白腻。",
            "无口臭。",
            "偶有粗糙感。有吸烟饮酒史30年。食欲可，大便成形。",
            "脉弦。",
            "淡暗", "白腻", "正常", "弦"
        ),
        "tcm_diag": (
            "白斑（苔藓样变）", "痰湿内蕴，气机不畅证",
            "烟酒长期刺激，痰湿内生，蕴结于口腔黏膜。舌淡暗苔白腻、脉弦为痰湿内蕴、气机不畅之表现。",
            "化痰软坚，理气活血"
        ),
        "tcm_rx": (
            "二陈汤合桃红四物汤加减",
            '[{"herb":"陈皮","dosage":"10g"},{"herb":"姜半夏","dosage":"10g"},{"herb":"茯苓","dosage":"15g"},{"herb":"甘草","dosage":"6g"},{"herb":"桃仁","dosage":"10g"},{"herb":"红花","dosage":"6g"},{"herb":"当归","dosage":"12g"},{"herb":"川芎","dosage":"10g"},{"herb":"赤芍","dosage":"12g"},{"herb":"丹参","dosage":"20g"},{"herb":"莪术","dosage":"10g"},{"herb":"浙贝母","dosage":"10g"}]',
            "每日1剂，加水浸泡30分钟，武火煮沸后文火煎30分钟，取汁200ml；二煎取汁150ml。两煎混合，分早晚两次温服。",
            '[{"condition":"白斑增厚明显","mod":"加三棱10g、海藻15g、昆布15g"},{"condition":"口苦苔黄","mod":"加黄连6g、黄芩10g"},{"condition":"体倦乏力","mod":"加黄芪20g、白术12g"}]',
            '[]',
            "无",
            "足三里、丰隆、血海、合谷（平补平泻，每周2次）"
        ),
    },
    "EM001": {
        "four_diag": (
            "口腔大面积糜烂、渗出明显，唇部暗褐厚血痂（特征性），舌红绛，苔黄腻。皮肤靶形红斑。面色红，急性病容。",
            "口臭明显，时有呻吟。",
            "口腔灼痛剧烈，不能进食，仅能饮少量温水。身热微恶寒，口干欲冷饮。小便黄少，大便3日未行。咽干痛。",
            "脉滑数有力。",
            "红绛", "黄腻", "正常", "滑数有力"
        ),
        "tcm_diag": (
            "猫眼疮（皮肤）+口糜（口腔）", "湿热毒蕴证",
            "口腔糜烂渗出重、皮肤靶形红斑、口臭、舌红苔黄腻、脉滑数为湿热毒蕴。外感风热加药物之毒，内外合邪，蕴结于肌肤黏膜。实证热证。",
            "清热利湿，凉血解毒"
        ),
        "tcm_rx": (
            "龙胆泻肝汤合五味消毒饮加减",
            '[{"herb":"龙胆草","dosage":"10g"},{"herb":"黄芩","dosage":"12g"},{"herb":"炒栀子","dosage":"10g"},{"herb":"泽泻","dosage":"10g"},{"herb":"通草","dosage":"6g"},{"herb":"车前子","dosage":"15g","special":"包煎"},{"herb":"当归","dosage":"10g"},{"herb":"生地黄","dosage":"20g"},{"herb":"柴胡","dosage":"10g"},{"herb":"生甘草","dosage":"10g"},{"herb":"金银花","dosage":"20g"},{"herb":"野菊花","dosage":"15g"},{"herb":"蒲公英","dosage":"30g"},{"herb":"紫花地丁","dosage":"15g"},{"herb":"紫背天葵","dosage":"15g"},{"herb":"生大黄","dosage":"6g","special":"后下"},{"herb":"牡丹皮","dosage":"12g"}]',
            "每日1剂，加水浸泡30分钟，武火煮沸后文火煎30分钟，取汁200ml；二煎取汁150ml。两煎混合，分早晚两次温服。",
            '[{"condition":"大便通畅后","mod":"去生大黄，改为制大黄6g（同煎）"},{"condition":"高热不退（>39℃）、舌红绛","mod":"加生石膏30g（先煎）、知母10g、水牛角30g（先煎）"},{"condition":"口腔糜烂渗出极重、口臭甚","mod":"加黄连6g（加量）、苦参10g、白鲜皮15g"},{"condition":"热退后正气已伤、乏力明显","mod":"去龙胆草减至6g、去大黄，加太子参15g、山药15g、生薏苡仁30g"}]',
            '[{"name":"清开灵颗粒","dosage":"10g","frequency":"tid","route":"冲服"}]',
            "金银花20g、连翘15g、黄连10g、黄柏10g、马齿苋30g，煎汤300ml，含漱5分钟后吐出，tid-qid。金黄散适量茶水调敷靶形红斑（无破溃处）qd。",
            "大椎、曲池、合谷、内庭、血海、委中（泻法）"
        ),
    },
    "ANUG001": {
        "four_diag": (
            "龈乳头'火山口'状坏死缺损，覆盖灰白色假膜。舌质红，苔黄腻。",
            "腐败性口臭（特征性）。",
            "牙龈剧痛、自发出血。发热38°C，全身乏力。口干，便秘。近期熬夜压力大。",
            "脉滑数。",
            "红", "黄腻", "正常", "滑数"
        ),
        "tcm_diag": (
            "牙疳", "胃火炽盛，热毒上攻证",
            "牙龈坏死、腐败性口臭、发热、舌红苔黄腻、脉滑数为胃火炽盛，热毒上攻。实证热证。",
            "清胃泻火，解毒凉血"
        ),
        "tcm_rx": (
            "清胃散合五味消毒饮加减",
            '[{"herb":"黄连","dosage":"10g"},{"herb":"升麻","dosage":"6g"},{"herb":"生地黄","dosage":"20g"},{"herb":"牡丹皮","dosage":"12g"},{"herb":"当归","dosage":"10g"},{"herb":"石膏","dosage":"30g","special":"先煎"},{"herb":"知母","dosage":"10g"},{"herb":"金银花","dosage":"20g"},{"herb":"野菊花","dosage":"15g"},{"herb":"蒲公英","dosage":"30g"},{"herb":"甘草","dosage":"6g"}]',
            "每日1剂，加水浸泡30分钟，武火煮沸后文火煎30分钟，取汁200ml；二煎取汁150ml。两煎混合，分早晚两次温服。",
            '[{"condition":"便秘严重","mod":"加生大黄10g（后下）、玄明粉6g（冲服）"},{"condition":"高热不退","mod":"加水牛角粉3g冲服"}]',
            '[]',
            "金银花20g、野菊花15g、黄连10g，煎汤200ml，含漱tid。",
            "合谷、内庭、颊车、下关、大椎（泻法）"
        ),
    },
    "LR001": {
        "four_diag": (
            "双侧颊黏膜沿咬合线白色网纹及线状糜烂，非典型放射状。舌质淡暗，苔薄白。",
            "无特殊。",
            "颊黏膜烧灼感，更换降压药后发病。口干不欲饮。纳可，大便成形。",
            "脉弦。",
            "淡暗", "薄白", "正常", "弦"
        ),
        "tcm_diag": (
            "口癣（苔藓样反应）", "药毒伤络，肝郁气滞证",
            "药物相关发病+沿咬合线分布+肝主疏泄，药毒伤及肝络。脉弦为肝郁气滞。",
            "疏肝理气，清热解毒"
        ),
        "tcm_rx": (
            "逍遥散加减",
            '[{"herb":"柴胡","dosage":"10g"},{"herb":"当归","dosage":"12g"},{"herb":"白芍","dosage":"15g"},{"herb":"白术","dosage":"10g"},{"herb":"茯苓","dosage":"15g"},{"herb":"薄荷","dosage":"6g","special":"后下"},{"herb":"炙甘草","dosage":"6g"},{"herb":"丹参","dosage":"15g"},{"herb":"白鲜皮","dosage":"15g"},{"herb":"牡丹皮","dosage":"10g"}]',
            "每日1剂，加水浸泡30分钟，武火煮沸后文火煎30分钟，取汁200ml；二煎取汁150ml。两煎混合，分早晚两次温服。",
            '[{"condition":"糜烂明显","mod":"加黄连6g、黄柏10g"},{"condition":"口干明显","mod":"加生地黄15g、麦冬15g"}]',
            '[]',
            "康复新液含漱tid。",
            "合谷、足三里、太冲、三阴交"
        ),
    },
    "ATOLP001": {
        "four_diag": (
            "弥漫性萎缩性红斑区与散在细微白色网状条纹混合。舌质偏红，苔薄少津。",
            "无口臭。",
            "口腔黏膜烧灼痛，进食辛辣加重，口干。糖尿病史。纳可，大便正常。",
            "脉细数。",
            "偏红", "薄少津", "正常", "细数"
        ),
        "tcm_diag": (
            "口癣（萎缩型）", "阴虚津亏，虚火上炎证",
            "舌红少津、口干、脉细数为阴虚津亏，虚火上炎。萎缩性改变为阴血不足、黏膜失养。",
            "滋阴生津，清热降火"
        ),
        "tcm_rx": (
            "知柏地黄丸合一贯煎加减",
            '[{"herb":"知母","dosage":"10g"},{"herb":"黄柏","dosage":"10g"},{"herb":"生地黄","dosage":"20g"},{"herb":"山茱萸","dosage":"12g"},{"herb":"山药","dosage":"15g"},{"herb":"茯苓","dosage":"15g"},{"herb":"牡丹皮","dosage":"10g"},{"herb":"泽泻","dosage":"10g"},{"herb":"北沙参","dosage":"15g"},{"herb":"麦冬","dosage":"15g"},{"herb":"枸杞子","dosage":"15g"},{"herb":"当归","dosage":"10g"},{"herb":"川�子","dosage":"6g"},{"herb":"石斛","dosage":"15g"}]',
            "每日1剂，加水浸泡30分钟，武火煮沸后文火煎30分钟，取汁200ml；二煎取汁150ml。两煎混合，分早晚两次温服。",
            '[{"condition":"烧灼感明显","mod":"加地骨皮15g、白薇10g"},{"condition":"口干甚","mod":"加天花粉15g、芦根30g"},{"condition":"血糖控制不佳","mod":"加黄芪30g、葛根15g"}]',
            '[{"name":"知柏地黄丸","dosage":"8粒","frequency":"tid","route":"口服"},{"name":"生脉饮","dosage":"10ml","frequency":"bid","route":"口服"}]',
            "养阴生肌散少许涂敷糜烂面bid。",
            "廉泉、地仓、合谷、足三里、三阴交、太溪"
        ),
    },
    "BP001": {
        "four_diag": (
            "口腔内小水疱疱壁较厚（张力性），糜烂面基底干净。舌质淡红，苔薄白。皮肤紧张性大疱。",
            "无特殊。",
            "口腔水疱反复发作3月，进食时不适。皮肤瘙痒性大疱。乏力，纳可。",
            "脉细。",
            "淡红", "薄白", "正常", "细"
        ),
        "tcm_diag": (
            "天疱疮（类天疱疮型）", "脾虚湿盛，气血不足证",
            "张力性水疱（非松弛性）、舌淡红、脉细为脾虚气血不足——与PV的湿热毒蕴不同。病位在脾，虚证为主。",
            "健脾益气，祛湿养血"
        ),
        "tcm_rx": (
            "参苓白术散合当归补血汤加减",
            '[{"herb":"党参","dosage":"15g"},{"herb":"白术","dosage":"12g"},{"herb":"茯苓","dosage":"15g"},{"herb":"山药","dosage":"15g"},{"herb":"黄芪","dosage":"30g"},{"herb":"当归","dosage":"12g"},{"herb":"白芍","dosage":"15g"},{"herb":"川芎","dosage":"10g"},{"herb":"生薏苡仁","dosage":"30g"},{"herb":"陈皮","dosage":"10g"},{"herb":"炙甘草","dosage":"6g"}]',
            "每日1剂，加水浸泡30分钟，武火煮沸后文火煎30分钟，取汁200ml；二煎取汁150ml。两煎混合，分早晚两次温服。",
            '[{"condition":"瘙痒明显","mod":"加白鲜皮15g、地肤子15g、苦参10g"},{"condition":"水疱多发","mod":"加土茯苓30g、白花蛇舌草15g"},{"condition":"骨质疏松明显","mod":"加杜仲12g、骨碎补15g"}]',
            '[]',
            "黄柏15g、苦参15g，煎汤含漱bid。",
            "足三里、脾俞、胃俞、血海、三阴交（补法）"
        ),
    },
}

def create_database():
    """创建数据库并填充示例数据"""
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.executescript(SCHEMA_SQL)

    for case in SAMPLE_CASES:
        hadm_id = case["hadm_id"]

        # 患者
        conn.execute(
            "INSERT INTO patients VALUES (NULL,?,?,?,?,?,?)",
            (hadm_id, *case["patient"]),
        )

        # 主诉
        conn.execute(
            "INSERT INTO chief_complaints VALUES (NULL,?,?,?,?,?)",
            (hadm_id, *case["chief_complaint"]),
        )

        # 口腔检查
        conn.execute(
            "INSERT INTO oral_examinations VALUES (NULL,?,?,?,?,?,?,?,?,?,?)",
            (hadm_id, *case["oral_exam"]),
        )

        # 化验
        conn.execute(
            "INSERT INTO lab_results VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (hadm_id, *case["lab"]),
        )

        # 微生物
        conn.execute(
            "INSERT INTO microbiology_results VALUES (NULL,?,?,?,?,?,?,?,?)",
            (hadm_id, *case["micro"]),
        )

        # 病理
        conn.execute(
            "INSERT INTO pathology_results VALUES (NULL,?,?,?,?,?,?)",
            (hadm_id, *case["pathology"]),
        )

        # 诊断
        conn.execute(
            "INSERT INTO diagnoses VALUES (NULL,?,?,?,?,?,?)",
            (hadm_id, *case["diagnosis"]),
        )

        # 治疗
        conn.execute(
            "INSERT INTO treatments VALUES (NULL,?,?,?,?,?,?,?)",
            (hadm_id, *case["treatment"]),
        )

        # 中医四诊
        tcm = TCM_DATA.get(hadm_id, {})
        if tcm:
            fd = tcm.get("four_diag", ("", "", "", "", "", "", "", ""))
            conn.execute(
                "INSERT INTO tcm_four_diagnosis VALUES (NULL,?,?,?,?,?,?,?,?,?)",
                (hadm_id, *fd),
            )
            td = tcm.get("tcm_diag", ("", "", "", ""))
            conn.execute(
                "INSERT INTO tcm_diagnoses VALUES (NULL,?,?,?,?,?)",
                (hadm_id, *td),
            )
            tr = tcm.get("tcm_rx", ("", "", "", "", "", "", ""))
            conn.execute(
                "INSERT INTO tcm_prescriptions VALUES (NULL,?,?,?,?,?,?,?,?)",
                (hadm_id, *tr),
            )

    conn.commit()
    conn.close()
    print(f"数据库已创建: {DATABASE_PATH} ({len(SAMPLE_CASES)} 例病例)")


def get_case(hadm_id: str) -> dict:
    """获取完整病例数据"""
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    tables = [
        "patients", "chief_complaints", "oral_examinations",
        "lab_results", "microbiology_results", "pathology_results",
        "diagnoses", "treatments"
    ]
    case = {}
    for table in tables:
        cursor.execute(f"SELECT * FROM {table} WHERE hadm_id = ?", (hadm_id,))
        row = cursor.fetchone()
        case[table] = dict(row) if row else {}

    conn.close()
    return case


def query_table(table: str, hadm_id: str) -> dict:
    """查询单表"""
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table} WHERE hadm_id = ?", (hadm_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}


def list_cases() -> list:
    """列出所有病例ID和诊断"""
    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.hadm_id, p.age, p.gender, d.primary_diagnosis, d.diagnosis_category
        FROM patients p
        JOIN diagnoses d ON p.hadm_id = d.hadm_id
        ORDER BY d.diagnosis_category
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_hpi_text(hadm_id: str) -> str:
    """获取病史叙述文本(模拟Patient Agent的知识来源)"""
    cc = query_table("chief_complaints", hadm_id)
    p = query_table("patients", hadm_id)
    if not cc or not p:
        return "患者信息不可用"

    systemic = json.loads(p.get("systemic_diseases", "[]"))
    return f"""现病史：
主诉：{cc.get('chief_complaint', 'N/A')}
发病时间：{cc.get('symptom_onset', 'N/A')}
病程：{cc.get('symptom_duration_days', 'N/A')}天
症状演变：{cc.get('symptom_evolution', 'N/A')}

既往史：{', '.join(s for s in systemic if s != 'none') or '无特殊'}
目前用药：{p.get('medications', 'N/A')}
药物过敏：{p.get('allergies', 'N/A')}"""


if __name__ == "__main__":
    create_database()
    print("\n病例列表:")
    for row in list_cases():
        print(f"  {row[0]} | {row[1]}岁 {row[2]} | {row[3]} | [{row[4]}]")
