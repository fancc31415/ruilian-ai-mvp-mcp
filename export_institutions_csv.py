"""
把 data/institutions.json 导出成CSV模板（data/institutions_template.csv），
方便在Excel/Numbers/WPS里直接编辑——保留现有种子数据作为起点，
你可以直接改掉不准的行、删掉不认识的机构、加你自己真实接触过的机构。

用法：
    python tools/export_institutions_csv.py

改完CSV之后，跑 tools/csv_to_institutions.py 转换回JSON。
"""
import csv
import json
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(ROOT_DIR, "data", "institutions.json")
CSV_PATH = os.path.join(ROOT_DIR, "data", "institutions_template.csv")

HEADERS = [
    "机构名称", "机构类型", "赛道覆盖", "投资阶段",
    "单笔规模下限_万元", "单笔规模上限_万元", "覆盖地区", "投资风格备注", "代表案例",
]
FIELD_MAP = {
    "机构名称": "name", "机构类型": "type", "赛道覆盖": "sectors", "投资阶段": "stages",
    "单笔规模下限_万元": "check_size_min_wan", "单笔规模上限_万元": "check_size_max_wan",
    "覆盖地区": "region", "投资风格备注": "style", "代表案例": "notable",
}
LIST_FIELDS = {"sectors", "stages"}


def export():
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        institutions = json.load(f)

    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HEADERS)
        for inst in institutions:
            row = []
            for cn_field in HEADERS:
                en_field = FIELD_MAP[cn_field]
                value = inst.get(en_field, "")
                if en_field in LIST_FIELDS:
                    value = "、".join(value) if isinstance(value, list) else value
                row.append(value)
            writer.writerow(row)

    print(f"✅ 已导出 {len(institutions)} 家机构到 {CSV_PATH}，可以用Excel打开编辑了")


if __name__ == "__main__":
    export()
