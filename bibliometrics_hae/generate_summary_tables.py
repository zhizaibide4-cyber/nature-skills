#!/usr/bin/env python3
"""
Generates comprehensive bibliometric statistical tables from the cleaned HAE datasets
(both the Strict PRISMA-filtered dataset N=377 and the Full non-retracted dataset N=453)
for direct inclusion in the SCI manuscript.
"""

import math
import os
import re
from collections import Counter, defaultdict

from clean_wos_hae import INSTITUTION_MAP, COUNTRY_MAP, parse_fields, parse_wos_records

OUT_DIR = "/workspace/bibliometrics_hae"
STRICT_PATH = os.path.join(OUT_DIR, "data_cleaned", "wos_hae_surgery_strict_cleaned.txt")
FULL_PATH = os.path.join(OUT_DIR, "data_cleaned", "wos_hae_surgery_full453_cleaned.txt")


def calc_h_index(citations):
    c_sorted = sorted(citations, reverse=True)
    h = 0
    for i, c in enumerate(c_sorted, 1):
        if c >= i:
            h = i
        else:
            break
    return h


def extract_countries_and_insts(data):
    countries = set()
    insts = set()
    for c1 in data.get("C1", []):
        c1_clean = re.sub(r"^\[.*?\]\s*", "", c1)
        parts = [x.strip() for x in c1_clean.split(",") if x.strip()]
        if parts:
            raw_c = parts[-1].rstrip(".")
            if "USA" in raw_c or re.match(r"^[A-Z]{2}\s+\d{5}", raw_c):
                raw_c = "USA"
            c_norm = COUNTRY_MAP.get(raw_c, raw_c)
            countries.add(c_norm)
            raw_inst = parts[0]
            inst_norm = INSTITUTION_MAP.get(raw_inst, raw_inst)
            insts.add(inst_norm)
    # Also check C3 for normalized institutions
    c3_text = " ".join(data.get("C3", []))
    for raw_c3 in [x.strip() for x in c3_text.split(";") if x.strip()]:
        if raw_c3 in INSTITUTION_MAP:
            insts.add(INSTITUTION_MAP[raw_c3])
    return countries, insts


def analyze_dataset(filepath):
    raw_recs = parse_wos_records(filepath)
    records = [parse_fields(r)[0] for r in raw_recs]

    total_pubs = len(records)
    total_citations = 0
    all_tc = []

    year_pubs = Counter()
    year_cites = Counter()
    dt_counts = Counter()

    country_pubs = Counter()
    country_cites = defaultdict(list)

    inst_pubs = Counter()
    inst_cites = defaultdict(list)

    author_pubs = Counter()
    author_cites = defaultdict(list)

    journal_pubs = Counter()
    journal_cites = defaultdict(list)

    de_counts = Counter()
    all_kw_counts = Counter()
    cr_counts = Counter()

    top_papers = []

    for d in records:
        py = int(d["PY"][0].strip()) if d.get("PY") and d["PY"][0].strip().isdigit() else 0
        tc = int(d["TC"][0].strip()) if d.get("TC") and d["TC"][0].strip().isdigit() else 0
        dt = " ".join(d.get("DT", [])).strip()
        so = " ".join(d.get("SO", [])).strip()
        ti = " ".join(d.get("TI", [])).strip()
        ut = d["UT"][0].strip() if d.get("UT") else ""
        first_au = d["AF"][0].strip() if d.get("AF") else "Unknown"

        total_citations += tc
        all_tc.append(tc)
        year_pubs[py] += 1
        year_cites[py] += tc
        dt_counts[dt] += 1

        countries, insts = extract_countries_and_insts(d)
        for c in countries:
            country_pubs[c] += 1
            country_cites[c].append(tc)
        for inst in insts:
            inst_pubs[inst] += 1
            inst_cites[inst].append(tc)

        for af in set(x.strip() for x in d.get("AF", []) if x.strip() and x.strip() != "[Anonymous]"):
            author_pubs[af] += 1
            author_cites[af].append(tc)

        if so:
            journal_pubs[so] += 1
            journal_cites[so].append(tc)

        de_kws = set()
        if d.get("DE"):
            for kw in " ".join(d["DE"]).split(";"):
                kw_s = kw.strip().lower()
                if kw_s:
                    de_counts[kw_s] += 1
                    de_kws.add(kw_s)

        id_kws = set()
        if d.get("ID"):
            for kw in " ".join(d["ID"]).split(";"):
                kw_s = kw.strip().lower()
                if kw_s:
                    id_kws.add(kw_s)

        for kw in (de_kws | id_kws):
            all_kw_counts[kw] += 1

        for cr in d.get("CR", []):
            cr_s = cr.strip()
            if cr_s:
                cr_counts[cr_s] += 1

        top_papers.append({
            "tc": tc,
            "py": py,
            "first_au": first_au,
            "ti": ti,
            "so": so,
            "ut": ut,
            "cpp_yr": round(tc / max(1, 2026 - py + 1), 2),
        })

    top_papers.sort(key=lambda x: (-x["tc"], x["py"]))

    return {
        "total_pubs": total_pubs,
        "total_citations": total_citations,
        "avg_citations": round(total_citations / max(1, total_pubs), 2),
        "h_index": calc_h_index(all_tc),
        "year_pubs": year_pubs,
        "year_cites": year_cites,
        "dt_counts": dt_counts,
        "country_pubs": country_pubs,
        "country_cites": country_cites,
        "inst_pubs": inst_pubs,
        "inst_cites": inst_cites,
        "author_pubs": author_pubs,
        "author_cites": author_cites,
        "journal_pubs": journal_pubs,
        "journal_cites": journal_cites,
        "de_counts": de_counts,
        "all_kw_counts": all_kw_counts,
        "cr_counts": cr_counts,
        "top_papers": top_papers,
    }


def main():
    s_stats = analyze_dataset(STRICT_PATH)
    f_stats = analyze_dataset(FULL_PATH)

    md = []
    md.append("# Bibliometric Data Cleaning & Statistical Summary Report")
    md.append("## Surgical Treatment of Hepatic Alveolar Echinococcosis (2000 – Oct 31, 2026)\n")

    md.append("### 1. Overview of PRISMA Screening & Dataset Metrics\n")
    md.append("| Metric | Raw Export | Full Cleaned (Non-retracted) | Strict PRISMA Cleaned (Core HAE Surgery) |")
    md.append("| :--- | :---: | :---: | :---: |")
    md.append(f"| Total Publications ($N$) | 456 | {f_stats['total_pubs']} | {s_stats['total_pubs']} |")
    md.append(f"| Total Citations | — | {f_stats['total_citations']} | {s_stats['total_citations']} |")
    md.append(f"| Mean Citations per Paper (CPP) | — | {f_stats['avg_citations']} | {s_stats['avg_citations']} |")
    md.append(f"| Dataset H-index | — | {f_stats['h_index']} | {s_stats['h_index']} |")
    md.append("| Retracted Publications Removed | 0 | 3 | 3 |")
    md.append("| Off-topic CE / Other Diseases Removed | 0 | 0 | 46 |")
    md.append("| Pure Veterinary / Preclinical Mouse-In Vitro Removed | 0 | 0 | 31 |")
    md.append("| Exclusively Extrahepatic / Non-surgical Removed | 0 | 0 | 14 |\n")

    n_s = s_stats["total_pubs"]
    n_f = f_stats["total_pubs"]

    md.append("### 2. Annual Publication and Citation Trends (2000–2026)\n")
    md.append(f"| Year | Strict Core Pubs ($N={n_s}$) | Strict Citations | Full Cleaned Pubs ($N={n_f}$) | Full Citations |")
    md.append("| :---: | :---: | :---: | :---: | :---: |")
    for y in range(2000, 2027):
        md.append(
            f"| {y} | {s_stats['year_pubs'][y]} | {s_stats['year_cites'][y]} | {f_stats['year_pubs'][y]} | {f_stats['year_cites'][y]} |"
        )
    md.append("")

    md.append("### 3. Top 12 Most Productive Countries/Regions\n")
    md.append(f"| Rank | Country | Core Pubs ($N={n_s}$) | % of {n_s} | Total Citations | CPP | H-index | Full Pubs ($N={n_f}$) |")
    md.append("| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
    for rank, (c, cnt) in enumerate(s_stats["country_pubs"].most_common(12), 1):
        cites = s_stats["country_cites"][c]
        tc_sum = sum(cites)
        cpp = round(tc_sum / cnt, 2)
        h = calc_h_index(cites)
        pct = round(cnt * 100.0 / s_stats["total_pubs"], 1)
        f_cnt = f_stats["country_pubs"][c]
        md.append(f"| {rank} | {c} | {cnt} | {pct}% | {tc_sum} | {cpp} | {h} | {f_cnt} |")
    md.append("")

    md.append("### 4. Top 12 Most Productive Institutions (After Standardization)\n")
    md.append(f"| Rank | Institution | Country | Core Pubs ($N={n_s}$) | Total Citations | CPP | H-index | Full Pubs ($N={n_f}$) |")
    md.append("| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: |")
    inst_country_lookup = {
        "Xinjiang Medical University": "China",
        "University of Franche-Comte / CHU Besancon": "France",
        "Sichuan University": "China",
        "Qinghai University": "China",
        "Ulm University": "Germany",
        "University of Bern": "Switzerland",
        "University of Zurich": "Switzerland",
        "Qinghai Provincial People's Hospital": "China",
        "World Health Organization": "Switzerland",
        "Ataturk University": "Turkey",
        "University of Geneva": "Switzerland",
        "Medical University of Warsaw": "Poland",
        "University of Alberta": "Canada",
        "Hacettepe University": "Turkey",
        "Hokkaido University": "Japan",
        "Asahikawa Medical University": "Japan",
    }
    filtered_insts = [(k, v) for k, v in s_stats["inst_pubs"].most_common(20) if k != "Univ Hosp"]
    for rank, (inst, cnt) in enumerate(filtered_insts[:12], 1):
        cites = s_stats["inst_cites"][inst]
        tc_sum = sum(cites)
        cpp = round(tc_sum / cnt, 2)
        h = calc_h_index(cites)
        f_cnt = f_stats["inst_pubs"][inst]
        c_label = inst_country_lookup.get(inst, "—")
        md.append(f"| {rank} | {inst} | {c_label} | {cnt} | {tc_sum} | {cpp} | {h} | {f_cnt} |")
    md.append("")

    md.append("### 5. Top 15 Most Productive Authors (After Disambiguation)\n")
    md.append(f"| Rank | Author (Standardized) | Core Pubs ($N={n_s}$) | Total Citations | CPP | H-index | Full Pubs ($N={n_f}$) |")
    md.append("| :---: | :--- | :---: | :---: | :---: | :---: | :---: |")
    for rank, (au, cnt) in enumerate(s_stats["author_pubs"].most_common(15), 1):
        cites = s_stats["author_cites"][au]
        tc_sum = sum(cites)
        cpp = round(tc_sum / cnt, 2)
        h = calc_h_index(cites)
        f_cnt = f_stats["author_pubs"][au]
        md.append(f"| {rank} | {au} | {cnt} | {tc_sum} | {cpp} | {h} | {f_cnt} |")
    md.append("")

    md.append("### 6. Top 15 Core Journals\n")
    md.append(f"| Rank | Journal | Core Pubs ($N={n_s}$) | Total Citations | CPP | H-index | Full Pubs ($N={n_f}$) |")
    md.append("| :---: | :--- | :---: | :---: | :---: | :---: | :---: |")
    for rank, (so, cnt) in enumerate(s_stats["journal_pubs"].most_common(15), 1):
        cites = s_stats["journal_cites"][so]
        tc_sum = sum(cites)
        cpp = round(tc_sum / cnt, 2)
        h = calc_h_index(cites)
        f_cnt = f_stats["journal_pubs"][so]
        md.append(f"| {rank} | {so} | {cnt} | {tc_sum} | {cpp} | {h} | {f_cnt} |")
    md.append("")

    md.append(f"### 7. Top 15 Most Cited Publications in Core HAE Surgery Dataset ($N={n_s}$)\n")
    md.append("| Rank | First Author (Year) | Title | Journal | Citations | Citations/Year |")
    md.append("| :---: | :--- | :--- | :--- | :---: | :---: |")
    for rank, p in enumerate(s_stats["top_papers"][:15], 1):
        md.append(f"| {rank} | {p['first_au']} ({p['py']}) | {p['ti']} | {p['so']} | {p['tc']} | {p['cpp_yr']} |")
    md.append("")

    md.append(f"### 8. Top 15 Most Frequently Co-Cited References ($N={n_s}$)\n")
    md.append(f"| Rank | Co-Cited Reference | Co-Citations (Core $N={n_s}$) | Co-Citations (Full $N={n_f}$) |")
    md.append("| :---: | :--- | :---: | :---: |")
    for rank, (cr, cnt) in enumerate(s_stats["cr_counts"].most_common(15), 1):
        f_cnt = f_stats["cr_counts"][cr]
        md.append(f"| {rank} | {cr} | {cnt} | {f_cnt} |")
    md.append("")

    md.append(f"### 9. Top 25 Standardized Author Keywords (DE) ($N={n_s}$)\n")
    md.append(f"| Rank | Standardized Author Keyword | Frequency (Core $N={n_s}$) | Frequency (Full $N={n_f}$) |")
    md.append("| :---: | :--- | :---: | :---: |")
    for rank, (kw, cnt) in enumerate(s_stats["de_counts"].most_common(25), 1):
        f_cnt = f_stats["de_counts"][kw]
        md.append(f"| {rank} | {kw} | {cnt} | {f_cnt} |")
    md.append("")

    out_md = os.path.join(OUT_DIR, "tables", "summary_tables.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"Summary tables written to {out_md}")


if __name__ == "__main__":
    main()
