#!/usr/bin/env python3
"""Write one Excel workbook for each step of the HAE cleaning pipeline.

The steps follow clean_wos_hae.main exactly: parse the raw export, standardize
fields, then apply the exclusion rules in the same order (retracted, veterinary
or preclinical, extrahepatic, no alveolar expression). A record is removed at
the first rule it hits.
"""

import copy
import os
import re
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

sys.path.insert(0, "/workspace/bibliometrics_hae")

from clean_wos_hae import (
    RAW_PATH,
    clean_html_entities,
    classify_record_for_prisma,
    parse_fields,
    parse_wos_records,
    standardize_author_af,
    standardize_author_au,
    standardize_keywords,
)
from generate_summary_tables import extract_countries_and_insts

OUT_DIR = "/workspace/bibliometrics_hae/excel"
STRICT_PATH = "/workspace/bibliometrics_hae/data_cleaned/wos_hae_surgery_strict_cleaned.txt"
FULL_PATH = "/workspace/bibliometrics_hae/data_cleaned/wos_hae_surgery_full453_cleaned.txt"

# Bibliographic fields, in Web of Science tag order. Anything else is appended.
TAGS = [
    ("UT", "UT_入藏号"),
    ("PT", "PT_文献类型代码"),
    ("AU", "AU_作者简称"),
    ("AF", "AF_作者全名"),
    ("TI", "TI_题名"),
    ("SO", "SO_期刊全称"),
    ("JI", "JI_ISO刊名"),
    ("J9", "J9_29字符刊名"),
    ("LA", "LA_语种"),
    ("DT", "DT_文献类型"),
    ("DE", "DE_作者关键词"),
    ("ID", "ID_KeywordsPlus"),
    ("AB", "AB_摘要"),
    ("C1", "C1_作者地址"),
    ("C3", "C3_增强机构"),
    ("RP", "RP_通讯作者"),
    ("EM", "EM_邮箱"),
    ("FU", "FU_基金"),
    ("FX", "FX_基金说明"),
    ("CR", "CR_参考文献"),
    ("NR", "NR_参考文献数"),
    ("TC", "TC_被引次数"),
    ("Z9", "Z9_总被引"),
    ("PY", "PY_出版年"),
    ("PD", "PD_出版日期"),
    ("EA", "EA_提前出版日期"),
    ("VL", "VL_卷"),
    ("IS", "IS_期"),
    ("BP", "BP_起始页"),
    ("EP", "EP_结束页"),
    ("AR", "AR_文献号"),
    ("DI", "DI_DOI"),
    ("WC", "WC_WebOfScience类别"),
    ("SC", "SC_研究方向"),
    ("PU", "PU_出版商"),
    ("PI", "PI_出版商城市"),
    ("PA", "PA_出版商地址"),
    ("SN", "SN_ISSN"),
    ("EI", "EI_eISSN"),
    ("OA", "OA_开放获取"),
    ("HC", "HC_高被引"),
    ("HP", "HP_热点"),
    ("DA", "DA_导出日期"),
]

ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
CELL_FONT = Font(name="Calibri", size=10)


def join_vals(vals):
    if not vals:
        return ""
    text = "\n".join(v.strip() for v in vals if v and v.strip())
    return ILLEGAL.sub("", text)


def apply_standardization(data, ordered_tags):
    """Same mutations as clean_wos_hae.main, on a copy."""
    data = copy.deepcopy(data)
    ordered_tags = list(ordered_tags)
    ut = data["UT"][0].strip() if data.get("UT") else ""

    if ut == "WOS:001605718300001":
        if "C1" not in data:
            data["C1"] = ["Ulm Univ Hosp, Dept Internal Med 3, Div Infect Dis, Ulm, Germany."]
            if "AB" in ordered_tags:
                ordered_tags.insert(ordered_tags.index("AB") + 1, "C1")
            else:
                ordered_tags.append("C1")
        if "C3" not in data:
            data["C3"] = ["Ulm University"]
            ordered_tags.insert(ordered_tags.index("C1") + 1, "C3")

    if "TI" in data:
        data["TI"] = [clean_html_entities(x) for x in data["TI"]]
    if "AB" in data:
        data["AB"] = [clean_html_entities(x) for x in data["AB"]]

    if "AF" in data:
        std_afs = [standardize_author_af(x) for x in data["AF"]]
        if "AU" in data and len(data["AU"]) == len(std_afs):
            data["AU"] = [standardize_author_au(au, af) for au, af in zip(data["AU"], std_afs)]
        elif "AU" in data:
            data["AU"] = [standardize_author_au(au) for au in data["AU"]]
        data["AF"] = std_afs

    if "DE" in data:
        std_de = standardize_keywords(data["DE"])
        data["DE"] = [std_de] if std_de else []
    if "ID" in data:
        std_id = standardize_keywords(data["ID"])
        data["ID"] = [std_id.upper()] if std_id else []

    if "C1" in data:
        new_c1 = []
        for line in data["C1"]:
            line = re.sub(r"Peoples R China", "China", line)
            line = re.sub(r"\bTurkiye\b", "Turkey", line)
            line = re.sub(r"\b(England|Scotland|Wales|North Ireland)\b", "United Kingdom", line)
            new_c1.append(line)
        data["C1"] = new_c1
    return data, ordered_tags


def record_row(data, extras):
    row = {}
    used = set()
    for tag, _header in TAGS:
        row[tag] = join_vals(data.get(tag, []))
        used.add(tag)
    leftovers = []
    for tag, vals in data.items():
        if tag in used:
            continue
        text = join_vals(vals)
        if text:
            leftovers.append(f"{tag}: {text}")
    row["OTHER"] = "\n".join(leftovers)
    row.update(extras)
    return row


def load_steps():
    raw_recs = parse_wos_records(RAW_PATH)
    raw_rows = []
    std_rows = []
    changes = []
    buckets = {
        "Excluded_Retracted": [],
        "Excluded_Veterinary_or_Preclinical": [],
        "Excluded_Extrahepatic_Only": [],
        "Excluded_OffTopic_CE_or_Other": [],
        "Included": [],
    }
    compare_tags = ["TI", "AB", "AU", "AF", "DE", "ID", "C1", "C3"]

    for idx, rec_text in enumerate(raw_recs, 1):
        original, ordered = parse_fields(rec_text)
        ut = original["UT"][0].strip() if original.get("UT") else f"REC_{idx}"
        standardized, _tags = apply_standardization(original, ordered)
        keep, category, reason = classify_record_for_prisma(standardized)
        countries, insts = extract_countries_and_insts(standardized)
        insts = sorted(i for i in insts if i != "Univ Hosp")
        fate = "纳入严格集" if keep else category
        extras_common = {
            "SEQ": idx,
            "FATE": fate,
            "REASON": reason,
            "COUNTRIES": "; ".join(sorted(countries)),
            "INSTITUTIONS": "; ".join(insts),
        }
        raw_rows.append(record_row(original, extras_common))
        std_row = record_row(standardized, extras_common)
        std_rows.append(std_row)
        buckets[category].append(std_row)

        for tag in compare_tags:
            before = join_vals(original.get(tag, []))
            after = join_vals(standardized.get(tag, []))
            if before != after:
                changes.append({
                    "SEQ": idx,
                    "UT": ut,
                    "PY": join_vals(original.get("PY", [])),
                    "TI": join_vals(standardized.get("TI", []))[:300],
                    "FIELD": tag,
                    "BEFORE": before,
                    "AFTER": after,
                })

    return raw_rows, std_rows, changes, buckets


def uts_from_wos(path):
    found = []
    for data, _tags in (parse_fields(rec) for rec in parse_wos_records(path)):
        if data.get("UT"):
            found.append(data["UT"][0].strip())
    return found


def write_table(path, headers, rows, sheet_name):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31]
    ws.append([header for _key, header in headers])
    for cell in ws[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    keys = [key for key, _header in headers]
    for row in rows:
        values = []
        for key in keys:
            value = row.get(key, "")
            if isinstance(value, str) and len(value) > 32767:
                raise SystemExit(f"Cell longer than Excel allows: {path} {key} {len(value)}")
            values.append(value)
        ws.append(values)
        for cell in ws[ws.max_row]:
            cell.font = CELL_FONT
            cell.alignment = Alignment(vertical="top", wrap_text=False)
    ws.auto_filter.ref = ws.dimensions
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{ws.max_row}"
    ws.row_dimensions[1].height = 22
    for col_idx, (_key, header) in enumerate(headers, 1):
        width = 18
        if any(token in header for token in ("题名", "摘要", "参考", "地址", "关键词", "标准化")):
            width = 46
        if "入藏号" in header or header.startswith("UT"):
            width = 24
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    ws.sheet_properties.tabColor = "1F4E78"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb.save(path)
    return ws.max_row - 1


RECORD_HEADERS = [("SEQ", "导出顺序")] + TAGS + [
    ("OTHER", "其他WoS字段"),
    ("FATE", "最终去向"),
    ("REASON", "筛选说明"),
    ("COUNTRIES", "分析用国家_地址末段加词表"),
    ("INSTITUTIONS", "分析用机构_词表归并"),
]

CHANGE_HEADERS = [
    ("SEQ", "导出顺序"),
    ("UT", "UT_入藏号"),
    ("PY", "PY_出版年"),
    ("TI", "TI_题名_截前300字"),
    ("FIELD", "改动字段"),
    ("BEFORE", "标准化前"),
    ("AFTER", "标准化后"),
]


def subset(rows, uts):
    wanted = set(uts)
    return [row for row in rows if row["UT"] in wanted]


def main():
    raw_rows, std_rows, changes, buckets = load_steps()
    retracted = buckets["Excluded_Retracted"]
    veterinary = buckets["Excluded_Veterinary_or_Preclinical"]
    extrahepatic = buckets["Excluded_Extrahepatic_Only"]
    offtopic = buckets["Excluded_OffTopic_CE_or_Other"]
    included = buckets["Included"]

    after_retraction = [row for row in std_rows if row["UT"] not in {r["UT"] for r in retracted}]
    removed_by_then = {r["UT"] for r in retracted + veterinary}
    after_vet = [row for row in after_retraction if row["UT"] not in removed_by_then]
    removed_by_then |= {r["UT"] for r in extrahepatic}
    after_extra = [row for row in after_vet if row["UT"] not in removed_by_then]
    final_rows = included

    expected = {
        "raw": 456,
        "std": 456,
        "retracted": 3,
        "after_retraction": 453,
        "veterinary": 31,
        "after_vet": 422,
        "extrahepatic": 14,
        "after_extra": 408,
        "offtopic": 46,
        "final": 362,
    }
    got = {
        "raw": len(raw_rows),
        "std": len(std_rows),
        "retracted": len(retracted),
        "after_retraction": len(after_retraction),
        "veterinary": len(veterinary),
        "after_vet": len(after_vet),
        "extrahepatic": len(extrahepatic),
        "after_extra": len(after_extra),
        "offtopic": len(offtopic),
        "final": len(final_rows),
    }
    if got != expected:
        raise SystemExit(f"Step counts do not match the pipeline: {got}")

    strict_uts = uts_from_wos(STRICT_PATH)
    full_uts = uts_from_wos(FULL_PATH)
    if [row["UT"] for row in final_rows] != [] and set(row["UT"] for row in final_rows) != set(strict_uts):
        raise SystemExit("Final Excel UT set differs from the strict WoS file")
    if len(strict_uts) != 362 or len(full_uts) != 453:
        raise SystemExit(f"Cleaned text files are not 362 and 453: {len(strict_uts)} {len(full_uts)}")
    if set(row["UT"] for row in after_retraction) != set(full_uts):
        raise SystemExit("Post-retraction Excel UT set differs from the 453-record file")

    # Keep the original export order inside every cumulative file.
    files = [
        ("01_全部原始数据_n456.xlsx", "原始456", RECORD_HEADERS, raw_rows),
        ("02_字段标准化后_尚未筛选_n456.xlsx", "标准化456", RECORD_HEADERS, std_rows),
        ("03_标准化改动明细.xlsx", "改动明细", CHANGE_HEADERS, changes),
        ("04_本步剔除_撤稿_n3.xlsx", "剔除撤稿", RECORD_HEADERS, retracted),
        ("05_剔除撤稿后_n453.xlsx", "剩余453", RECORD_HEADERS, after_retraction),
        ("06_本步剔除_兽医与临床前_n31.xlsx", "剔除兽医临床前", RECORD_HEADERS, veterinary),
        ("07_剔除兽医与临床前后_n422.xlsx", "剩余422", RECORD_HEADERS, after_vet),
        ("08_本步剔除_纯肝外_n14.xlsx", "剔除纯肝外", RECORD_HEADERS, extrahepatic),
        ("09_剔除纯肝外后_n408.xlsx", "剩余408", RECORD_HEADERS, after_extra),
        ("10_本步剔除_无泡型表达_n46.xlsx", "剔除无泡型表达", RECORD_HEADERS, offtopic),
        ("11_清洗后_严格纳入_n362.xlsx", "严格纳入362", RECORD_HEADERS, final_rows),
    ]

    written = []
    for filename, sheet, headers, rows in files:
        path = os.path.join(OUT_DIR, filename)
        n = write_table(path, headers, rows, sheet)
        written.append((filename, n, sheet))
        print(f"{filename}: {n} rows")

    index_rows = [
        {"STEP": "0", "FILE": "01_全部原始数据_n456.xlsx", "N": 456,
         "WHAT": "Web of Science 纯文本导出的全部记录。字段保持导出原貌，尚未改作者、关键词、国名或 HTML。"},
        {"STEP": "1", "FILE": "02_字段标准化后_尚未筛选_n456.xlsx", "N": 456,
         "WHAT": "同一 456 条，已去掉题名和摘要中的 HTML、统一作者与关键词、把地址里的 Peoples R China / Turkiye / 英国构成国改成分析用国名，并补上匿名乌尔姆论文的地址。这一步还不删记录。"},
        {"STEP": "1b", "FILE": "03_标准化改动明细.xlsx", "N": len(changes),
         "WHAT": "第 1 步里实际发生变化的字段，一行一个字段，列出改前和改后。没有改动的记录不出现在这个文件里。"},
        {"STEP": "2", "FILE": "04_本步剔除_撤稿_n3.xlsx", "N": 3,
         "WHAT": "文献类型为撤稿，或题名标明 Retracted / Withdrawn。从这里开始，一条记录只进入它命中的第一个剔除文件。"},
        {"STEP": "2b", "FILE": "05_剔除撤稿后_n453.xlsx", "N": 453,
         "WHAT": "456 减去 3 篇撤稿。与 data_cleaned/wos_hae_surgery_full453_cleaned.txt 是同一批入藏号。"},
        {"STEP": "3", "FILE": "06_本步剔除_兽医与临床前_n31.xlsx", "N": 31,
         "WHAT": "题名命中预先写定的兽医或小鼠、大鼠、体外抗寄生虫实验规则。"},
        {"STEP": "3b", "FILE": "07_剔除兽医与临床前后_n422.xlsx", "N": 422,
         "WHAT": "453 减去 31。"},
        {"STEP": "4", "FILE": "08_本步剔除_纯肝外_n14.xlsx", "N": 14,
         "WHAT": "预先写定的 14 个入藏号：肺、脾、肾上腺、心、脑、腮腺或非外科的过敏/肾病主题。"},
        {"STEP": "4b", "FILE": "09_剔除纯肝外后_n408.xlsx", "N": 408,
         "WHAT": "422 减去 14。"},
        {"STEP": "5", "FILE": "10_本步剔除_无泡型表达_n46.xlsx", "N": 46,
         "WHAT": "题名、摘要、作者关键词都没有泡型包虫表达，而且不在 7 篇地标豁免名单里。Keywords Plus 单独出现不算。"},
        {"STEP": "6", "FILE": "11_清洗后_严格纳入_n362.xlsx", "N": 362,
         "WHAT": "408 减去 46。这是论文的分析集，与 data_cleaned/wos_hae_surgery_strict_cleaned.txt 是同一批入藏号。其中 7 篇本身不含泡型表达，因豁免名单保留。"},
    ]
    index_headers = [
        ("STEP", "步骤"),
        ("FILE", "文件"),
        ("N", "行数_不含表头"),
        ("WHAT", "这一步是什么"),
    ]
    write_table(os.path.join(OUT_DIR, "00_步骤说明.xlsx"), index_headers, index_rows, "步骤说明")
    print(f"00_步骤说明.xlsx: {len(index_rows)} steps; change rows {len(changes)}")

    # The change log must contain the known author inversions.
    changed_af = " ".join(row["AFTER"] for row in changes if row["FIELD"] == "AF")
    for name in ("Wen, Hao", "Aji, Tuerganaili", "Ran, Bo"):
        if name not in changed_af:
            raise SystemExit(f"Change log is missing standardized author {name}")


if __name__ == "__main__":
    main()
