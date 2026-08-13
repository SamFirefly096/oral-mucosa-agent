"""
知识库检索模块
供反思阶段调用：根据Agent的诊断假设，从知识库中检索相关疾病的标准信息，
用于外部知识锚定验证。

策略：关键词匹配 + 诊断名称精确查找 + 临床表现交叉检索
无需向量化——11种疾病的关键词检索已足够准确。
"""
import json
import re
from pathlib import Path
from typing import Optional

KB_PATH = Path(__file__).resolve().parent / "data" / "knowledge_base.json"


class KnowledgeBaseRetriever:
    """教科书知识库检索器"""

    def __init__(self):
        with open(KB_PATH, "r", encoding="utf-8") as f:
            self.kb = json.load(f)
        self.diseases = self.kb["diseases"]
        self.tcm = self.kb["tcm_knowledge"]
        self.dd_rules = self.kb["differential_diagnosis_rules"]

    # ── 精准检索：按诊断名称 ──
    def search_by_diagnosis(self, diagnosis_text: str) -> Optional[dict]:
        """根据Agent的诊断名查找对应疾病条目"""
        text_lower = diagnosis_text.lower()

        # 精确key匹配
        key_map = {
            "oral_lichen": "oral_lichen_planus",
            "lichen_planus": "oral_lichen_planus",
            "olp": "oral_lichen_planus",
            "扁平苔藓": "oral_lichen_planus",
            "口癣": "oral_lichen_planus",
            "pemphigus_vulgaris": "pemphigus_vulgaris",
            "pemphigus": "pemphigus_vulgaris",
            "pv": "pemphigus_vulgaris",
            "天疱疮": "pemphigus_vulgaris",
            "火赤疮": "pemphigus_vulgaris",
            "bullous_pemphigoid": "bullous_pemphigoid",
            "bp": "bullous_pemphigoid",
            "类天疱疮": "bullous_pemphigoid",
            "candidiasis": "oral_candidiasis",
            "念珠菌": "oral_candidiasis",
            "鹅口疮": "oral_candidiasis",
            "aphthous": "recurrent_aphthous",
            "ras": "recurrent_aphthous",
            "阿弗他": "recurrent_aphthous",
            "口疮": "recurrent_aphthous",
            "疱疹": "herpes_simplex",
            "hsv": "herpes_simplex",
            "龈口炎": "herpes_simplex",
            "discoid_lupus": "discoid_lupus",
            "dle": "discoid_lupus",
            "红斑狼疮": "discoid_lupus",
            "唇风": "discoid_lupus",
            "erythema_multiforme": "erythema_multiforme",
            "em": "erythema_multiforme",
            "多形红斑": "erythema_multiforme",
            "猫眼疮": "erythema_multiforme",
            "leukoplakia": "leukoplakia",
            "白斑": "leukoplakia",
            "anug": "anug",
            "坏死性溃疡性龈炎": "anug",
            "坏死性龈炎": "anug",
            "牙疳": "anug",
            "lichenoid": "lichenoid_reaction",
            "苔藓样反应": "lichenoid_reaction",
        }

        for keyword, disease_key in key_map.items():
            if keyword in text_lower:
                return self.diseases.get(disease_key)
        return None

    # ── 模糊检索：按临床表现关键词 ──
    def search_by_symptoms(self, symptom_text: str) -> list[dict]:
        """根据临床表现关键词检索可能相关的疾病"""
        results = []
        text_lower = symptom_text.lower()

        keyword_disease_map = {
            "wickham": ["oral_lichen_planus"],
            "nikolsky.*阳|nikolsky.*posit": ["pemphigus_vulgaris"],
            "nikolsky.*阴|nikolsky.*negat": ["bullous_pemphigoid", "oral_lichen_planus", "erythema_multiforme"],
            "白色假膜|可擦除|凝乳|curd": ["oral_candidiasis"],
            "不可擦除|白斑(?!.*可擦)": ["leukoplakia"],
            "反复.*溃.*疡|recurrent.*ulcer|aphthous": ["recurrent_aphthous"],
            "成簇.*水疱|发热.*水疱|cluster.*vesicle": ["herpes_simplex"],
            "三区|放射状白纹|毛细血管扩张|萎缩.*白纹": ["discoid_lupus"],
            "靶形|target.*lesion|出血性.*痂|血痂": ["erythema_multiforme"],
            "火山口|坏死.*龈|腐败.*臭|fetid.*odor": ["anug"],
            "张力性.*水疱|tense.*(bull|blister)": ["bullous_pemphigoid"],
            "松弛性.*水疱|flaccid.*(bull|blister)": ["pemphigus_vulgaris"],
            "龈乳头.*坏死|punched.*papill": ["anug"],
            "咬合线|药物.*换.*降压|lichenoid|苔藓样": ["lichenoid_reaction"],
            "日晒.*加重|sun.*exposure|photosensitiv": ["discoid_lupus"],
            "抗生素.*诱|antibiotic.*induc|糖尿病.*口腔|diabetes.*oral": ["oral_candidiasis"],
            "双侧.*对称.*颊|bilateral.*buccal.*striae": ["oral_lichen_planus"],
            "棘层松解|acantholysis|墓碑状|tombstone": ["pemphigus_vulgaris"],
            "表皮下.*疱|subepithelial.*(bull|blister)": ["bullous_pemphigoid"],
        }

        matched_keys = set()
        for pattern, disease_keys in keyword_disease_map.items():
            if re.search(pattern, text_lower):
                for dk in disease_keys:
                    matched_keys.add(dk)

        for dk in matched_keys:
            disease = self.diseases.get(dk)
            if disease:
                results.append(disease)
        return results

    # ── 组合检索（推荐反思阶段使用）──
    def retrieve_for_reflection(self,
                                 primary_diagnosis: str,
                                 differential_diagnoses: list[str] = None,
                                 clinical_findings: str = "") -> dict:
        """
        反思阶段的综合检索

        返回:
        {
            "primary_match": {...},       # 主要诊断匹配的疾病条目
            "dd_matches": [...],          # 鉴别诊断匹配的条目
            "symptom_matches": [...],     # 临床表现匹配的可能疾病
            "diagnostic_checklist": [...], # 诊断核查要点
            "retrieval_summary": str       # 检索结果摘要(注入反思提示)
        }
        """
        result = {
            "primary_match": None,
            "dd_matches": [],
            "symptom_matches": [],
            "diagnostic_checklist": [],
            "retrieval_summary": "",
        }

        # 1. 精准检索主要诊断
        primary = self.search_by_diagnosis(primary_diagnosis)
        if primary:
            result["primary_match"] = {
                "name_cn": primary["name_cn"],
                "tcm_disease": primary.get("tcm_disease_name", ""),
                "tcm_syndromes": primary.get("tcm_syndromes", {}),
            }

        # 2. 检索鉴别诊断
        if differential_diagnoses:
            for dd in differential_diagnoses:
                match = self.search_by_diagnosis(dd)
                if match:
                    result["dd_matches"].append({
                        "name_cn": match["name_cn"],
                        "key_features": match.get("clinical_features", [])[:3],
                    })

        # 3. 临床表现交叉检索
        if clinical_findings:
            symptom_matches = self.search_by_symptoms(clinical_findings)
            result["symptom_matches"] = [
                {"name_cn": m["name_cn"], "relevance": "临床表现匹配"}
                for m in symptom_matches
                if not primary or m["name_cn"] != primary.get("name_cn")
            ]

        # 4. 构建诊断核查要点
        if primary:
            result["diagnostic_checklist"] = self._build_checklist(primary, result["symptom_matches"])

        # 5. 生成检索摘要
        result["retrieval_summary"] = self._format_summary(result)
        return result

    def _build_checklist(self, primary: dict, symptom_matches: list) -> list[str]:
        """构建诊断核查要点列表"""
        checklist = []
        crit = primary.get("diagnostic_criteria", {})
        dd_list = primary.get("differential_diagnoses", [])

        # 临床标准
        clinical = crit.get("clinical", [])
        if clinical:
            checklist.append(f"[诊断标准核查] {primary['name_cn']}的临床标准: {'; '.join(clinical[:3])}")

        # 病理标准
        pathology = crit.get("pathology", [])
        if pathology:
            checklist.append(f"[病理标准] {pathology[0][:80]}...")

        # 关键鉴别
        key_diff = primary.get("key_differentiation", {})
        for dd_name, diff_point in list(key_diff.items())[:2]:
            checklist.append(f"[关键鉴别] {diff_point[:100]}")

        # 临床表现交叉验证
        if symptom_matches:
            alternative_names = [m["name_cn"] for m in symptom_matches[:3]]
            checklist.append(f"[临床表现交叉匹配] 临床表现也符合: {', '.join(alternative_names)}，请确认已充分排除")

        return checklist

    def _format_summary(self, result: dict) -> str:
        """格式化为反思提示中可注入的检索摘要"""
        parts = []

        if result["primary_match"]:
            pm = result["primary_match"]
            parts.append(f"【知识库检索结果：{pm['name_cn']}】")
            if pm.get("tcm_disease"):
                parts.append(f"  中医病名：{pm['tcm_disease']}")
            tcm_syn = pm.get("tcm_syndromes", {})
            if tcm_syn:
                for subtype, syndromes in tcm_syn.items():
                    parts.append(f"  标准证型({subtype})：{', '.join(syndromes)}")
            if result["diagnostic_checklist"]:
                parts.append("  核查要点：")
                for item in result["diagnostic_checklist"][:4]:
                    parts.append(f"    {item}")

        if result["dd_matches"]:
            parts.append(f"\n【待排除的鉴别诊断】")
            for dd in result["dd_matches"][:3]:
                parts.append(f"  - {dd['name_cn']}: {', '.join(dd.get('key_features', []))}")

        if result["symptom_matches"]:
            parts.append(f"\n【临床表现交叉匹配】以下疾病临床表现也符合，请确保鉴别排除：")
            for m in result["symptom_matches"][:3]:
                parts.append(f"  - {m['name_cn']}")

        if not parts:
            return "（知识库中未找到精准匹配，请基于教科书知识进行判断）"

        return "\n".join(parts)


# ── 全局单例 ──
_retriever = None


def get_retriever() -> KnowledgeBaseRetriever:
    global _retriever
    if _retriever is None:
        _retriever = KnowledgeBaseRetriever()
    return _retriever
