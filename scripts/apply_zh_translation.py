#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把数据库中的英文检查/病史表述替换为中文（幂等，可重复执行）。

用法：
    python3 scripts/apply_zh_translation.py            # 应用 i18n/zh_terms_map.json
    python3 scripts/apply_zh_translation.py --dry-run  # 只报告将修改的单元格数

背景：口腔检查/化验/微生物/病理/既往史等字段原为英文（源于病例报告 PDF 抽取），
会直接出现在医生 Agent 的检查结果里。本脚本按映射表做精确匹配替换，涉及：
  oral_examinations(9列) / lab_results(3列) / microbiology_results(4列) / pathology_results(1列)
  patients.systemic_diseases(JSON数组逐项)
映射表由模型翻译 + 人工校对生成，保留数字、单位、牙位编号与英文缩写。
"""
import argparse, json, os, re, sqlite3, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "oral_mucosa.db")
MAP = os.path.join(ROOT, "i18n", "zh_terms_map.json")

TARGETS = {
    "oral_examinations": ["lesion_location", "lesion_morphology", "lesion_size_mm", "lesion_color",
                          "lesion_texture", "nikolsky_sign", "extraoral_findings", "oral_hygiene",
                          "additional_notes"],
    "lab_results": ["ana", "anti_desmoglein1", "anti_desmoglein3"],
    "microbiology_results": ["fungal_smear", "fungal_culture", "hsv_pcr", "bacterial_culture"],
    "pathology_results": ["biopsy_site"],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not os.path.exists(DB):
        sys.exit(f"未找到数据库：{DB}")
    tr = json.load(open(MAP, encoding="utf-8"))
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    cells = 0
    for t, cols in TARGETS.items():
        for r in db.execute(f"SELECT * FROM {t}"):
            d = dict(r); upd = {}
            for c in cols:
                v = str(d.get(c) or "").strip()
                if v in tr and tr[v] and tr[v] != v:
                    upd[c] = tr[v]
            if upd:
                cells += len(upd)
                if not a.dry_run:
                    sets = ", ".join(f"{c}=?" for c in upd)
                    db.execute(f"UPDATE {t} SET {sets} WHERE id=?", list(upd.values()) + [d["id"]])
    # 既往史 JSON 数组逐项替换
    for r in db.execute("SELECT hadm_id, systemic_diseases FROM patients"):
        try:
            arr = json.loads(r[1] or "[]")
        except Exception:
            continue
        new = [tr.get(str(x).strip(), x) for x in arr]
        if new != arr:
            cells += 1
            if not a.dry_run:
                db.execute("UPDATE patients SET systemic_diseases=? WHERE hadm_id=?",
                           (json.dumps(new, ensure_ascii=False), r[0]))
    if not a.dry_run:
        db.commit()
    print(f"{'[dry-run] 将修改' if a.dry_run else '已修改'} {cells} 个单元格/字段")


if __name__ == "__main__":
    main()
