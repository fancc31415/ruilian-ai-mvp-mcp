"""
机构数据 CSV → JSON 转换工具。

现在的机构库（data/institutions.json）是公开信息拼的种子库，精度有限。
真正提升匹配准确度最有效的办法，是换成你手上真实成交/接触过的机构数据——
但直接手改JSON容易漏逗号、漏引号导致格式错误。这个脚本让你改CSV（Excel能直接编辑）就行，
改完跑一下这个脚本，自动生成规范的 institutions.json。

用法：
    1. 打开 data/institutions_template.csv，用Excel/Numbers/WPS编辑（或者直接在里面新增行）
    2. 跑：python tools/csv_to_institutions.py
    3. 会在 data/institutions.json 生成更新后的文件（自动备份旧版本为 institutions.json.bak）

CSV里"赛道覆盖"和"投资阶段"两列，多个值用中文顿号"、"分隔，比如：人工智能、企业服务/SaaS
"""
import csv
import json
import os
import shutil

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT_DIR, "data", "institutions_template.csv")
JSON_PATH = os.path.join(ROOT_DIR, "data", "institutions.json")

FIELD_MAP = {
    "机构名称": "name",
    "机构类型": "type",
    "赛道覆盖": "sectors",
    "投资阶段": "stages",
    "单笔规模下限_万元": "check_size_min_wan",
    "单笔规模上限_万元": "check_size_max_wan",
    "覆盖地区": "region",
    "投资风格备注": "style",
    "代表案例": "notable",
}
LIST_FIELDS = {"sectors", "stages"}
NUMBER_FIELDS = {"check_size_min_wan", "check_size_max_wan"}


def convert():
    if not os.path.exists(CSV_PATH):
        print(f"找不到CSV文件：{CSV_PATH}")
        print("先跑一次 python tools/export_institutions_csv.py 生成模板，再编辑它。")
        return

    institutions = []
    with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=2):  # 第1行是表头，数据从第2行开始
            if not row.get("机构名称", "").strip():
                continue  # 跳过空行

            inst = {}
            for cn_field, en_field in FIELD_MAP.items():
                raw_value = (row.get(cn_field) or "").strip()
                if en_field in LIST_FIELDS:
                    inst[en_field] = [v.strip() for v in raw_value.split("、") if v.strip()]
                elif en_field in NUMBER_FIELDS:
                    try:
                        inst[en_field] = float(raw_value) if raw_value else 0
                        if inst[en_field] == int(inst[en_field]):
                            inst[en_field] = int(inst[en_field])
                    except ValueError:
                        print(f"⚠️ 第{row_num}行「{row.get('机构名称')}」的「{cn_field}」不是有效数字：{raw_value!r}，已记为0")
                        inst[en_field] = 0
                else:
                    inst[en_field] = raw_value
            institutions.append(inst)

    if not institutions:
        print("CSV里没有读到任何有效数据，检查一下是不是表头名字改动过、或者所有行都是空的。")
        return

    if os.path.exists(JSON_PATH):
        shutil.copy(JSON_PATH, JSON_PATH + ".bak")
        print(f"已备份旧版本到 {JSON_PATH}.bak")

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(institutions, f, ensure_ascii=False, indent=2)

    print(f"✅ 转换完成，共 {len(institutions)} 家机构，已写入 {JSON_PATH}")


if __name__ == "__main__":
    convert()
