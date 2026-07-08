"""
王雨田八年制学生病例报告 — 10个口腔黏膜病病例
运行：python wang_cases.py
将新病例追加到现有数据库（跳过已存在的病例）。
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "oral_mucosa.db"

# ── 10个病例 ────────────────────────────────────────
WANG_CASES = [
    # ===== 1. 放射性口腔黏膜炎（放射回忆效应）=====
    {
        "hadm_id": "ROM001",
        "patient": (53, "M",
            '["nasopharyngeal_carcinoma","cervical_lymph_node_metastasis","type2_diabetes"]',
            "胰岛素（15年史）", "无"),
        "chief_complaint": (
            "右颊黏膜溃烂伴剧痛2月，进食困难伴体重下降15kg",
            "2月前（放疗开始1月后）出现右颊黏膜溃烂",
            60,
            "鼻咽癌放疗史：VMAT，GTVnd 69.96Gy/33f，CTV 60.06Gy/33f。放疗前未行口腔评估，未拔除阻生牙。放疗开始1月后出现右颊溃烂，持续不愈。曾用卡拉胶含漱液+利多卡因止痛无效。精神压力大，睡眠差，夜间痛醒，便秘。近2月体重下降15kg。"
        ),
        "oral_exam": (
            "right_buccal_mucosa",
            "ulcer,erosion,edema",
            "18号牙对应颊黏膜1×1cm²溃烂面",
            "表面黄白假膜，周围水肿、充血",
            "溃烂面柔软，未触及硬结",
            "not_tested",
            "none",
            "poor",
            "张口度一横指。口腔卫生差，牙石(++)。溃烂面边缘水肿充血明显。未及硬结或肿块。"
        ),
        "lab": (None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None),
        "micro": (None, None, None, None, None, None, None),
        "pathology": (
            "right_buccal_mucosa",
            "黏膜组织，小唾液腺泡萎缩，间质水肿明显，局灶性炎细胞浸润，邻近黏膜上皮修复活跃",
            None,
            None,
            "符合放射性口腔黏膜炎改变"
        ),
        "diagnosis": (
            "放射性口腔黏膜炎（放射回忆效应）(Radiation-induced Oral Mucositis, Radiation Recall)",
            '["放射性骨坏死","肿瘤复发口腔侵犯","感染性口腔溃疡"]',
            "DA01.1",
            "radiation_induced_oral_mucositis",
            '{"clinical":"放疗史+颊黏膜顽固性溃烂+时间关联(放疗后1月)","pathology":"小唾液腺萎缩+间质水肿+炎细胞浸润","exclusion":"无肿瘤复发证据(影像学)"}'
        ),
        "treatment": (
            '{"povidone_iodine_solution":"10ml gargle tid","oral_care_gel":"0.2g tid topical","lidocaine_gel":"0.5g prn topical"}',
            '{"none":"no systemic medication indicated"}',
            '{"glycemic_control":"内分泌科会诊","oral_care_education":"口腔护理指导","behavioral":"避免辛辣烫食"}',
            "治疗4周后溃疡明显缩小，疼痛明显缓解，张口度恢复至二指",
            "no",
            "放射性口腔黏膜炎通常自限。NCCN指南建议放疗前口腔评估+拔除病灶牙。放疗前未行口腔准备的患者ROM风险可能增加55%。"
        ),
    },
    # ===== 2. 口腔白斑（PDT治疗，与LEUK001不同患者）=====
    {
        "hadm_id": "LEUK002",
        "patient": (36, "M",
            '["allergic_rhinitis"]',
            "无", "无"),
        "chief_complaint": (
            "左舌下区白色斑块1年",
            "1年前发现左舌下区白色斑块",
            365,
            "1年前发现左舌下区白色斑块，无疼痛不适。外院临床诊断'白斑'，未予治疗。吸烟10年，5-6支/日，偶尔饮酒。精神压力大，睡眠尚可。"
        ),
        "oral_exam": (
            "left_ventral_tongue,floor_of_mouth",
            "plaque_homogeneous_white",
            "左舌腹口底2处：1.5×1.2cm²和1.2×1.5cm²",
            "白色均质，不可擦除",
            "表面光滑，边界清晰，未触及硬结",
            "not_tested",
            "none",
            "fair",
            "Velscope检查：白-暗区。均质型白斑，边界清晰但不规则。口腔卫生一般，牙石(+)。"
        ),
        "lab": (None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None),
        "micro": (None, None, None, None, None, None, None),
        "pathology": (
            "left_ventral_tongue",
            "鳞状上皮增生伴过度角化（正角化），上皮无异型增生",
            None,
            None,
            "口腔白斑（均质型），无异型增生"
        ),
        "diagnosis": (
            "口腔白斑（均质型，无异型增生）(Oral Leukoplakia, Homogeneous, No Dysplasia)",
            '["摩擦性角化","口腔扁平苔藓(斑块型)","白色海绵状斑痣"]',
            "DA01.0",
            "leukoplakia",
            '{"clinical":"不可擦除白色均质斑块+吸烟史+Velscope暗区","pathology":"过度角化+无异型增生(关键)","site":"左舌腹口底"}'
        ),
        "treatment": (
            '{"none":"topical treatment not indicated for homogeneous leukoplakia without dysplasia"}',
            '{"none":"no systemic medication for low-risk leukoplakia"}',
            '{"ALA_PDT":"5-氨基酮戊酸光动力治疗(ALA-PDT)，共8次(470mW,632nm激光，每病灶照射4分钟)","smoking_cessation":"强烈建议戒烟","regular_followup":"每3-6月随访"}',
            "PDT 8次后随访1年无明显复发。Velscope复查白斑区域缩小",
            "no",
            "均质型白斑无异型增生恶变风险<5%。ALA-PDT为新兴治疗手段，中华口腔医学会2024年发布PDT治疗口腔潜在恶性疾病专家共识。"
        ),
    },
    # ===== 3. 寻常型天疱疮（与PV001不同患者）=====
    {
        "hadm_id": "PV002",
        "patient": (48, "F",
            '["hypertension"]',
            "无", "无"),
        "chief_complaint": (
            "口腔黏膜糜烂反复发作2月，伴皮肤水疱广泛分布",
            "2月前无明显诱因出现口腔黏膜糜烂",
            60,
            "2月前出现口腔黏膜糜烂，伴皮肤水疱。5天前外院诊断'病毒感染'，康复新液含漱无效。眼部、生殖器无皮疹。精神压力大，睡眠差，便秘。"
        ),
        "oral_exam": (
            "bilateral_buccal_mucosa,gingiva,palate_soft,tongue_lateral,floor_of_mouth,parotid_duct_orifice",
            "erosion,bulla,desquamative_gingivitis,edema",
            "多处糜烂面：颊部0.6×3cm²，软腭3×2cm²",
            "鲜红糜烂面，周围环状水肿，边缘扩展性",
            "糜烂面柔软，尼氏征边缘扩展",
            "positive",
            "skin_bullae_on_trunk_and_limbs",
            "poor",
            "44-47颊侧牙龈及颊黏膜0.6×3cm²浅表糜烂面。颊黏膜多处环状水肿。舌侧缘7-8个绿豆大水疱。口底腮腺导管开口处水疱。舌腹0.4×1.5cm²糜烂。牙石(+++)，38/28阻生。"
        ),
        "lab": (None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None),
        "micro": ("negative", None, "negative", None, None, None, None),
        "pathology": (
            "left_buccal_mucosa_perilesional",
            "表皮内水疱，棘层松解细胞(Tzanck细胞)可见，基底细胞呈墓碑状排列于真皮乳头上",
            "IgG和C3沿棘细胞间网状沉积（鱼网状）",
            None,
            "符合寻常型天疱疮"
        ),
        "diagnosis": (
            "寻常型天疱疮 (Pemphigus Vulgaris)",
            '["瘢痕性类天疱疮","大疱性类天疱疮","副肿瘤性天疱疮"]',
            "EB40.0",
            "pemphigus_vulgaris",
            '{"clinical":"口腔+皮肤水疱+Nikolsky征阳性+剥脱性龈炎","pathology":"棘层松解+墓碑状基底细胞","DIF":"IgG/C3棘细胞间网状沉积","serology":"抗Dsg3:155.26RU/mL(升高),抗Dsg1/BP180/BP230阴性"}'
        ),
        "treatment": (
            '{"triamcinolone_acetonide_0.1pct_ointment":"bid topical","chlorhexidine_mouthwash":"bid","sodium_bicarbonate_gargle":"3g+100ml water tid"}',
            '{"prednisolone":"起始4片tid(60mg/d)，16个月内递减至1片qd(5mg/d)维持","nystatin":"50万IU tid (激素期间预防真菌)"}',
            '{"periodontal_treatment":"牙周洁治+拔除28/38","calcium_vitaminD":"补充","gastric_protection":"质子泵抑制剂","ophthalmology_consult":"眼科基线检查(羟氯喹)"}',
            "每2-4周调整激素剂量。递减方案：4-4-3→4-4-2→6-2→5/4→3/4→2/3→1/2片，总疗程16月。随访期内无复发",
            "no",
            "规范激素治疗预后良好。本例16月成功递减至5mg/d维持。长期激素需监测血糖、血压、骨密度。激素助减可考虑MMF或CD20单抗。"
        ),
    },
    # ===== 4. 带状疱疹（三叉神经下颌支）=====
    {
        "hadm_id": "HZ001",
        "patient": (55, "M",
            '["allergic_rhinitis"]',
            "无", "无"),
        "chief_complaint": (
            "左下唇阵发性剧痛4天，伴面部皮疹和低热",
            "4天前咬硬物后出现左下唇自发性剧痛",
            4,
            "左下唇剧痛放射至面部和颌下区，低热37.6℃，偶头痛。3天前外院诊断'感染'，口服头孢拉定2天无效。精神压力大，睡眠差。"
        ),
        "oral_exam": (
            "left_lower_lip,left_perioral_skin,left_buccal_mucosa,tongue_dorsal",
            "vesicle_clustered,erosion,crust,pseudomembrane",
            "左下唇+口周皮肤3×4cm²散在成簇水疱",
            "透明水疱，部分破溃结痂，周围红斑",
            "成簇水疱，疱壁薄，部分破溃",
            "not_tested",
            "left_facial_skin_vesicles_and_crusts,left_perioral_crusts",
            "fair",
            "左下唇/口周3×4cm²散在成簇水疱、结痂。左口角及唇周2×4cm²散在水疱。左颊3×4cm²假膜。左颊0.3×0.4cm²糜烂。舌背散在浅表糜烂。单侧受累（左三叉神经下颌支分布区）。"
        ),
        "lab": (None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None),
        "micro": (None, None, None, None, None, None, None),
        "pathology": (None, None, None, None, None),
        "diagnosis": (
            "带状疱疹（三叉神经下颌支）(Herpes Zoster, Trigeminal Mandibular Branch)",
            '["单纯疱疹","三叉神经痛","过敏性口炎","急性牙髓炎"]',
            "1E91",
            "herpes_zoster",
            '{"clinical":"单侧沿神经分布的成簇水疱+剧痛+低热","distribution":"左下唇→面部皮肤→口内颊黏膜(三叉神经下颌支)","differential_from_HSV":"单侧三叉神经节段分布(非双侧)"}'
        ),
        "treatment": (
            '{"chlorhexidine_mouthwash":"bid gargle","gentamicin_dexamethasone_ointment":"bid topical","acyclovir_ointment":"bid topical"}',
            '{"valacyclovir/acyclovir":"口服抗病毒(发病72h内最佳)","vitamin_C":"supplement"}',
            '{"pain_management":"必要时镇痛","skin_care":"保持皮疹区清洁干燥"}',
            "1周后复诊：皮疹大部分消退结痂，疼痛明显减轻。唇周皮肤开始愈合",
            "no",
            "预后良好，皮疹2-3周愈合。约10-15%可遗留带状疱疹后神经痛(PHN)，早期抗病毒治疗可降低PHN风险。"
        ),
    },
    # ===== 5. 多形红斑（口腔为主型，与EM001不同患者）=====
    {
        "hadm_id": "EM002",
        "patient": (25, "M",
            '["none"]',
            "无", "无"),
        "chief_complaint": (
            "双唇糜烂血痂伴口腔多发性糜烂8天，发热3天",
            "8天前无明显诱因出现口腔不适，初为唇部水疱",
            8,
            "8天前口腔不适。6天前外院皮肤科诊断'疱疹'，用阿昔洛韦口服+外用、头孢+清热解毒片。3天前发热38.6℃，咽部疼痛，结膜炎。外院CRP 27.05mg/L。甲流/乙流/支原体/新冠均阴性。精神压力大，焦虑，睡眠差。"
        ),
        "oral_exam": (
            "lips_diffuse,bilateral_buccal_mucosa,gingiva,palate_soft,tongue",
            "erosion_extensive,crust_hemorrhagic,erythema,ulcer,edema",
            "弥漫性累及双唇、双颊、牙龈、软腭",
            "唇部暗褐血痂，口腔内弥漫性充血糜烂",
            "糜烂面柔软，触痛明显",
            "not_tested",
            "target_lesions_on_hands_and_forearms",
            "fair",
            "下唇弥漫性充血、糜烂、血痂。上唇充血、糜烂、血痂。双颊弥漫性充血，双侧磨牙区糜烂。软腭充血+散在糜烂。手指及前臂可见靶形红斑（同心圆三层结构）。"
        ),
        "lab": (None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None),
        "micro": (None, None, None, None, None, None, None),
        "pathology": (None, None, None, None, None),
        "diagnosis": (
            "多形红斑（口腔为主型）(Erythema Multiforme, Oral-predominant)",
            '["Stevens-Johnson综合征","原发性疱疹性龈口炎","手口足病","过敏性口炎"]',
            "EB12",
            "erythema_multiforme",
            '{"clinical":"靶形红斑+口腔糜烂+口唇血痂+结膜炎+发热","epidemiology":"青年男性+应激+疑似感染触发(CRP升高)","exclusion":"皮肤剥脱<10%排除SJS"}'
        ),
        "treatment": (
            '{"lidocaine_gel":"prn topical for pain before meals","compound_chlorhexidine_gargle":"bid","gentamicin_dexamethasone_ointment":"bid topical"}',
            '{"prednisolone":"30mg qd po for 1 week then taper","vitamin_C+acyclovir":"precautionary"}',
            '{"hydration":"积极补液","ophthalmology_consult":"眼科会诊(结膜炎)","dermatology_consult":"必要时皮肤科会诊"}',
            "1周后复诊：糜烂明显好转，唇部血痂脱落。继续递减激素",
            "no",
            "多数预后良好，2-4周恢复。需排除SJS。复发型可能与HSV再激活相关，可考虑阿昔洛韦预防。"
        ),
    },
    # ===== 6. 过敏性口炎 =====
    {
        "hadm_id": "AOU001",
        "patient": (23, "M",
            '["none"]',
            "艾司唑仑（安眠药，常服）", "无"),
        "chief_complaint": (
            "下唇内侧黏膜多发性糜烂伴剧痛3天",
            "3天前夜班工作压力大、失眠后出现",
            3,
            "3天前夜班压力大、睡眠极差后，下唇内侧黏膜出现多发性糜烂20余个，米粒至绿豆大小，剧痛，张口受限。双唇肿胀伴渗出。平素精神压力大。"
        ),
        "oral_exam": (
            "lower_labial_mucosa,bilateral_buccal_mucosa,palate_hard,gingiva",
            "erosion_multiple,ulcer_small,edema,erythema",
            "下唇内侧散在20余个米粒至绿豆大小糜烂面",
            "糜烂面覆黄白假膜，周围充血明显",
            "糜烂面柔软，触痛明显",
            "not_tested",
            "bilateral_lip_swelling,scattered_facial_erythema",
            "fair",
            "双唇肿胀、渗出，散在面部红斑。下唇内侧散在20余个米粒至绿豆大小糜烂面。硬腭3×3cm²浅表糜烂。48颊黏膜0.2×0.2cm²糜烂。18/28/38/48阻生。牙石(+)。"
        ),
        "lab": (None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None),
        "micro": (None, None, None, None, None, None, None),
        "pathology": (None, None, None, None, None),
        "diagnosis": (
            "过敏性口炎 (Allergic Oral Stomatitis)",
            '["复发性阿弗他口炎","多形红斑","疱疹性口炎","接触性过敏性口炎"]',
            "DA01.1",
            "allergic_oral_ulceration",
            '{"clinical":"急性发作多发性糜烂(20+个)+唇肿胀+压力/失眠诱因","exclusion":"无靶形红斑排除EM,无成簇水疱排除HSV,无反复发作史排除RAS"}'
        ),
        "treatment": (
            '{"lidocaine_gel":"0.5g prn topical before meals","compound_chlorhexidine_gargle":"10ml bid","gentamicin_dexamethasone_ointment":"0.2g tid topical","lactate_ethacridine_solution":"10ml bid wet compress"}',
            '{"prednisolone":"5mg submucosal injection (单次)","chlorpheniramine_maleate":"12g tid po"}',
            '{"saline_rinse":"10ml bid gargle","vitamin_C":"supplement","oral_hygiene":"口腔卫生指导"}',
            "1周后复诊：面部红肿消退，口内糜烂大部分愈合，张口受限缓解",
            "no",
            "去除过敏原后预后良好。避免接触可能过敏原。压力管理和规律作息有助于预防复发。"
        ),
    },
    # ===== 7. 重型复发性阿弗他溃疡（MajRAS）=====
    {
        "hadm_id": "MRAS001",
        "patient": (48, "M",
            '["gastritis_20yrs"]',
            "无", "无"),
        "chief_complaint": (
            "口腔糜烂反复发作3年，每次持续2-8周",
            "3年前开始反复发作口腔糜烂",
            1095,
            "3年前开始反复发作口腔糜烂，无间歇期，每次2-5个，位于舌缘和腭部。糜烂大而深（>1cm），持续2-8周，疼痛严重。无眼部、关节、生殖器溃疡或皮损。6月前ANA(+)1:?、ESR 34mm/h。秋水仙碱口服1月无效。吸烟史20年(10支/日)，已戒4年。偶饮啤酒。"
        ),
        "oral_exam": (
            "lower_labial_mucosa,left_tongue_lateral,hard_palate,gingiva",
            "ulcer_large_deep,erosion,erythema",
            "下唇内侧1.2×0.6cm²深大糜烂面",
            "糜烂面覆黄白假膜，周围充血明显",
            "糜烂面边界清晰，触痛明显",
            "not_tested",
            "none",
            "poor",
            "下唇内侧1.2×0.6cm²深大糜烂面。舌侧缘3个小糜烂。硬腭散在小糜烂。15-17/24-26/35-37固定桥，47全冠，48阻生。口腔卫生差，牙石(+++)。"
        ),
        "lab": (None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None),
        "micro": (None, None, None, None, None, None, None),
        "pathology": (None, None, None, None, None),
        "diagnosis": (
            "重型复发性阿弗他溃疡 (Major Recurrent Aphthous Stomatitis, MaRAS)",
            '["白塞病","寻常型天疱疮","克罗恩病口腔表现","创伤性溃疡"]',
            "DA01.1",
            "major_recurrent_aphthous",
            '{"clinical":"反复深大溃疡(>1cm)+持续2-8周+瘢痕愈合+秋水仙碱无效","exclusion":"无眼部/生殖器/关节/皮肤病变排除白塞病,无胃肠道症状排除克罗恩病"}'
        ),
        "treatment": (
            '{"triamcinolone_acetonide_0.1pct_in_orabase":"0.2g tid topical","compound_chlorhexidine_gargle":"10ml bid"}',
            '{"colchicine":"50mg tid po, 服3天停4天","chlorpheniramine_maleate":"12g tid po"}',
            '{"periodontal_treatment":"牙周洁治","oral_hygiene_instruction":"口腔卫生指导","stress_management":"压力管理"}',
            "每2周复查血常规+空腹血糖。若6-8周无效考虑沙利度胺或TNF-α抑制剂",
            "no",
            "重型RAS较难控制，可能需免疫调节治疗。秋水仙碱无效可升级为沙利度胺或生物制剂。排除潜在系统性疾病。"
        ),
    },
    # ===== 8. 口腔苔藓样病变（OLL）=====
    {
        "hadm_id": "OLL001",
        "patient": (33, "F",
            '["allergic_rhinitis","hyperthyroidism"]',
            "无", "无"),
        "chief_complaint": (
            "口腔粗糙不适3月，进食刺激性食物时疼痛",
            "3月前接触石膏类材料（狮子头小雕塑）后出现",
            90,
            "半年前开始接触石膏类小雕塑，3月前出现口腔粗糙不适、口干，辛辣食物刺激痛。1月前外院诊断'扁平苔藓'，康复新液含漱无效。伴甲亢病史，焦虑，睡眠差。无明显体重变化。"
        ),
        "oral_exam": (
            "bilateral_buccal_mucosa,lower_labial_mucosa,tongue_dorsal,tongue_lateral,palate",
            "plaque_white_spongy,reticular_striae",
            "双侧颊黏膜广泛雪白色斑块",
            "雪白色，不可擦除",
            "柔软海绵状，粗糙感",
            "not_tested",
            "none",
            "fair",
            "双颊及下唇内侧黏膜广泛雪白色斑块。舌背及边缘、腭部散在白色斑块。非典型Wickham纹（与OLP不同）。口腔卫生一般，牙石(+)。"
        ),
        "lab": (None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None),
        "micro": ("negative", None, "negative", None, None, None, None),
        "pathology": (
            "left_buccal_mucosa",
            "符合口腔苔藓样病变，上皮下带状淋巴细胞浸润，无真菌感染",
            None,
            None,
            "符合口腔苔藓样病变(OLL)"
        ),
        "diagnosis": (
            "口腔苔藓样病变 (Oral Lichenoid Lesion, OLL)",
            '["口腔扁平苔藓","白色海绵状斑痣","慢性咬颊症","接触性过敏性口炎"]',
            "DA01.1",
            "oral_lichenoid_lesion",
            '{"clinical":"非典型白色病变+可疑石膏接触史+无典型Wickham纹","pathology":"苔藓样病变,无真菌","differential_from_OLP":"可疑接触性病因+非放射状白纹"}'
        ),
        "treatment": (
            '{"triamcinolone_acetonide_0.2pct_injection":"局部注射(单次)","tacrolimus_ointment":"bid topical"}',
            '{"none":"no systemic medication"}',
            '{"vitamin_B1":"supplement","vitamin_A":"supplement","avoid_allergen":"避免接触可疑过敏材料(石膏/粉尘)"}',
            "用药1月后粗糙感、刺激痛明显好转。白色斑块未完全消退但自觉症状显著改善",
            "no",
            "OLL去除致病因素后可能消退。与OLP的关键鉴别：①接触史②非典型Wickham纹③去除刺激后消退。需定期随访。"
        ),
    },
    # ===== 9. 白色海绵状斑痣 (White Sponge Nevus) =====
    {
        "hadm_id": "WSN001",
        "patient": (49, "M",
            '["atrophic_gastritis"]',
            "无", "无"),
        "chief_complaint": (
            "左颊黏膜发白1周",
            "1周前发现左颊黏膜发白",
            7,
            "1周前偶然发现左颊黏膜发白，无自发性痛及刺激痛。精神压力大，睡眠可，二便正常。否认吸烟饮酒。父亲有'双颊发白'类似病史。"
        ),
        "oral_exam": (
            "bilateral_buccal_mucosa_diffuse",
            "plaque_white_spongy,thickened",
            "左颊全部5×7cm²；右颊全部4.5×7cm²",
            "白色，弥漫性肿胀增厚",
            "柔软海绵状，边界不清，无压痛",
            "not_tested",
            "none",
            "poor",
            "左颊全部黏膜5×7cm²肿胀发白，轻度增厚，边界不清，触之柔软无压痛。右颊全部4.5×7cm²同样改变。双侧对称。不可擦除。口腔卫生差，牙石(++)。"
        ),
        "lab": (None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None),
        "micro": (None, None, None, None, None, None, None),
        "pathology": (
            "left_buccal_mucosa",
            "上皮增生伴海绵状结构，符合白色海绵状斑痣",
            None,
            None,
            "符合白色海绵状斑痣(White Sponge Nevus)"
        ),
        "diagnosis": (
            "白色海绵状斑痣 (White Sponge Nevus)",
            '["口腔白斑","口腔扁平苔藓","遗传性良性上皮内角化不良","白色水肿"]',
            "DA01.0",
            "white_sponge_nevus",
            '{"clinical":"弥漫性白色海绵状双侧对称病变+柔软不可擦除+自幼/家族史","pathology":"上皮增生伴海绵状结构","inheritance":"常染色体显性遗传(父亲类似病史)","key_differential":"柔软海绵状(非硬结)+双侧对称+不可擦除"}'
        ),
        "treatment": (
            '{"chlorhexidine_mouthwash":"bid gargle (post-biopsy care)"}',
            '{"none":"no systemic treatment required"}',
            '{"genetic_counseling":"向患者解释良性遗传性质，缓解癌变恐惧","regular_followup":"定期口腔检查"}',
            "活检后1周复诊。无需特殊治疗。向患者解释良性性质后焦虑明显缓解",
            "no",
            "良性常染色体显性遗传病，预后良好，一般无需干预。角蛋白4/13基因突变所致。可累及口腔、消化道、生殖道黏膜。"
        ),
    },
    # ===== 10. 慢性唇炎 =====
    {
        "hadm_id": "CC001",
        "patient": (19, "M",
            '["dust_allergy"]',
            "无", "无"),
        "chief_complaint": (
            "唇部反复干燥脱屑、起疱伴瘙痒2年",
            "2年前开始唇部反复干燥脱屑",
            730,
            "2年前开始唇部反复干燥脱屑，伴瘙痒，搔抓后疼痛。上海某医院诊断'唇炎'，中药湿敷1月好转后停药。2月后复发，自行水+乳酸依沙吖啶溶液湿敷，未用软膏保护。初有效，后期无效。发病后有舔唇习惯。精神、睡眠、食欲、二便正常。"
        ),
        "oral_exam": (
            "lips_diffuse,perioral_skin,bilateral_commissures",
            "erythema,scale,crack,crust,angular_cheilitis",
            "口周约18×10cm²红斑鳞屑区",
            "唇部干燥发红，鳞屑，皲裂",
            "干燥粗糙，触痛敏感",
            "not_tested",
            "perioral_red_scaly_skin_18x10cm,left_jaw_0.3x3cm_blood_crust",
            "fair",
            "口周约18×10cm²红色鳞屑性皮损。左下颏0.3×3cm²血痂。双唇干燥、发红、鳞屑、皲裂，触痛。双口角发白、鳞屑、皲裂、压痛（口角炎）。张口度三指。其他口腔黏膜无异常。"
        ),
        "lab": (None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None),
        "micro": (None, None, None, None, None, None, None),
        "pathology": (None, None, None, None, None),
        "diagnosis": (
            "慢性唇炎 (Chronic Cheilitis)",
            '["光化性唇炎","腺性唇炎","过敏性接触性唇炎","肉芽肿性唇炎","浆细胞性唇炎"]',
            "DA01.1",
            "chronic_cheilitis",
            '{"clinical":"唇部反复干燥脱屑皲裂2年+舔唇习惯+不规范湿敷史","exclusion":"无明确光敏史排除光化性唇炎,无唇部弥漫性肿胀排除肉芽肿性唇炎","key":"湿敷后未用软膏保护是关键治疗失败原因"}'
        ),
        "treatment": (
            '{"lactate_ethacridine_solution_0.1pct":"湿敷20分钟 tid（饭后）,期间持续补充药液保持饱和","compound_gentamicin_hydrochloride_ointment":"湿敷后立即涂抹保护"}',
            '{"none":"no systemic medication"}',
            '{"lip_care_education":"标准化湿敷教学+湿敷后必须用软膏保护(关键)","behavior_modification":"戒除舔唇/撕咬唇部死皮","maintenance":"症状缓解后逐步过渡为清水湿敷+凡士林保护"}',
            "1周后复诊：面部血痂及皮损愈合，唇部无干燥脱屑。6月后线上随访无复发",
            "no",
            "规范湿敷治疗是慢性唇炎治疗的关键。临床医师需亲自示范湿敷方法并教育患者。湿敷后软膏保护是治疗成功的前提。"
        ),
    },
]


def add_cases():
    """将王雨田病例报告中的10个病例加入数据库"""
    if not DB_PATH.exists():
        print(f"错误：数据库不存在 {DB_PATH}")
        print("请先运行: python -c \"from database import create_database; create_database()\"")
        return

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # 检查已有病例
    existing = set()
    cursor.execute("SELECT hadm_id FROM patients")
    for row in cursor.fetchall():
        existing.add(row[0])

    added = 0
    skipped = 0

    for case in WANG_CASES:
        hadm_id = case["hadm_id"]
        if hadm_id in existing:
            print(f"  跳过: {hadm_id} (已存在)")
            skipped += 1
            continue

        try:
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
            print(f"  OK: {hadm_id} — {case['diagnosis'][0][:60]}")
            added += 1
        except Exception as e:
            print(f"  失败: {hadm_id} — {e}")
            conn.rollback()
            return

    conn.commit()

    # 验证
    cursor.execute("SELECT COUNT(*) FROM patients")
    total = cursor.fetchone()[0]
    print(f"\n数据库现有 {total} 例病例 (新增 {added}, 跳过 {skipped})")

    # 列出全部
    print("\n当前数据库全部病例:")
    print(f"{'ID':<12} {'年龄':<6} {'性别':<6} {'诊断类别':<38} {'诊断'}")
    print("-" * 120)
    cursor.execute("""
        SELECT p.hadm_id, p.age, p.gender, d.primary_diagnosis, d.diagnosis_category
        FROM patients p JOIN diagnoses d ON p.hadm_id = d.hadm_id ORDER BY p.id
    """)
    for row in cursor.fetchall():
        gender = '女' if row[2] == 'F' else '男'
        print(f"  {row[0]:<12} {row[1]}岁  {gender:<5} [{row[4]:<36}] {row[3][:55]}")

    conn.close()
    print("\n完成。")


if __name__ == "__main__":
    add_cases()
