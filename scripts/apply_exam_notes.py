#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把口腔检查的「补充说明」等字段统一为纯客观查体所见（幂等，可重复执行）。

用法：
    python3 scripts/apply_exam_notes.py            # 写入 i18n/exam_notes_objective.json 的内容
    python3 scripts/apply_exam_notes.py --dry-run  # 只报告会修改多少字段

背景：原记录里混有诊断结论（如「符合急性过敏性接触性唇炎」「诊断为毛舌」「鉴别需排除…」
「特征性/典型表现」等），学生做鉴别诊断时等于直接看到答案。
本脚本按已审核的文本替换为「只有客观所见」的版本：保留部位、大小、形态、质地、触痛、
牙位与修复体位置关系、激发试验与患者反应、阴性所见与卫生状况；删除诊断名称、诊断结论、
鉴别诊断、病因归因与判断性措辞。数字、单位、牙位编号与材料名称原样保留。
"""
import argparse, json, os, sqlite3, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "oral_mucosa.db")
DATA = os.path.join(ROOT, "i18n", "exam_notes_objective.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not os.path.exists(DB):
        sys.exit(f"未找到数据库：{DB}")
    data = json.load(open(DATA, encoding="utf-8"))
    db = sqlite3.connect(DB)
    n = 0
    for h, cols in data.items():
        for c, v in cols.items():
            row = db.execute(f"SELECT {c} FROM oral_examinations WHERE hadm_id=?", (h,)).fetchone()
            if row and str(row[0] or "") != v:
                n += 1
                if not a.dry_run:
                    db.execute(f"UPDATE oral_examinations SET {c}=? WHERE hadm_id=?", (v, h))
    if not a.dry_run:
        db.commit()
    print(f"{'[dry-run] 将修改' if a.dry_run else '已修改'} {n} 个字段")


if __name__ == "__main__":
    main()
