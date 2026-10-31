#!/usr/bin/env python3
"""Build the submission draft (Word + Markdown) from the strict HAE corpus.

Every count in the prose is computed here or read from the figure source files
and checked against a fresh computation. The Web of Science topic-search string
is not in the export and is left as an author placeholder.
"""

import csv
import math
import os
import re
import sys
from collections import Counter, defaultdict
from itertools import combinations

import matplotlib
import networkx
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor, Twips

sys.path.insert(0, "/workspace/bibliometrics_hae")

from clean_wos_hae import clean_html_entities, parse_fields, parse_wos_records
from generate_figures_part2 import THEMES, compute_callon_metrics, record_keywords
from generate_summary_tables import calc_h_index, extract_countries_and_insts

BASE = "/workspace/bibliometrics_hae"
STRICT = os.path.join(BASE, "data_cleaned", "wos_hae_surgery_strict_cleaned.txt")
FULL = os.path.join(BASE, "data_cleaned", "wos_hae_surgery_full453_cleaned.txt")
FIG = os.path.join(BASE, "figures")
SRC = os.path.join(BASE, "source_data")
OUT_DOCX = os.path.join(BASE, "manuscript", "HAE_Surgical_Bibliometrics_Manuscript_2000_2026.docx")
OUT_MD = os.path.join(BASE, "manuscript", "HAE_Surgical_Bibliometrics_Manuscript_2000_2026.md")

AE_PAT = re.compile(
    r"(alveolar\s*echinococc\w*|alveolar\s*hydatid\w*|echinococcus\s*multilocularis|"
    r"e\.\s*multilocularis|e-multilocularis|multilocular\s*echinococc\w*|"
    r"multilocular\s*hydatid\w*|echinococcus\s*alveolaris|alveococcosis|\bhae\b)",
    re.I,
)

JOURNAL_ABBR = {
    "ACTA TROPICA": "Acta Trop",
    "CLINICAL MICROBIOLOGY REVIEWS": "Clin Microbiol Rev",
    "JOURNAL OF HEPATOLOGY": "J Hepatol",
    "TRENDS IN PARASITOLOGY": "Trends Parasitol",
    "CURRENT OPINION IN INFECTIOUS DISEASES": "Curr Opin Infect Dis",
    "EUROPEAN JOURNAL OF GASTROENTEROLOGY & HEPATOLOGY": "Eur J Gastroenterol Hepatol",
    "TRANSPLANTATION": "Transplantation",
    "BJS-BRITISH JOURNAL OF SURGERY": "Br J Surg",
    "CHINESE MEDICAL JOURNAL": "Chin Med J (Engl)",
    "EXPERT REVIEW OF ANTI-INFECTIVE THERAPY": "Expert Rev Anti Infect Ther",
    "INTERNATIONAL JOURNAL OF SURGERY": "Int J Surg",
    "FRONTIERS IN MEDICINE": "Front Med (Lausanne)",
    "AMERICAN JOURNAL OF TRANSPLANTATION": "Am J Transplant",
    "LANGENBECKS ARCHIVES OF SURGERY": "Langenbecks Arch Surg",
    "LIVER TRANSPLANTATION": "Liver Transpl",
    "WORLD JOURNAL OF SURGERY": "World J Surg",
    "JOURNAL OF THE AMERICAN COLLEGE OF SURGEONS": "J Am Coll Surg",
    "SURGERY": "Surgery",
    "WORLD JOURNAL OF GASTROENTEROLOGY": "World J Gastroenterol",
    "INTERNATIONAL JOURNAL OF INFECTIOUS DISEASES": "Int J Infect Dis",
    "CLINICAL INFECTIOUS DISEASES": "Clin Infect Dis",
    "PARASITE": "Parasite",
    "PLOS NEGLECTED TROPICAL DISEASES": "PLoS Negl Trop Dis",
    "WORLD JOURNAL OF GASTROINTESTINAL SURGERY": "World J Gastrointest Surg",
    "ASIAN JOURNAL OF SURGERY": "Asian J Surg",
    "EUROPEAN JOURNAL OF MEDICAL RESEARCH": "Eur J Med Res",
    "SEMINARS IN LIVER DISEASE": "Semin Liver Dis",
}

# WoS lists three names for this consensus; the writing panel is larger.
FORCE_ET_AL = {"10.1016/j.actatropica.2009.11.001"}
# This record's SO is the book title. The series is Advances in Parasitology, vol. 96.
BOOK_SERIES = {"10.1016/bs.apar.2016.09.006": "Adv Parasitol"}

EXTERNAL_REFS = {
    "page2021": (
        "Page MJ, McKenzie JE, Bossuyt PM, et al. The PRISMA 2020 statement: an updated "
        "guideline for reporting systematic reviews. BMJ. 2021;372:n71. doi:10.1136/bmj.n71"
    ),
    "hirsch2005": (
        "Hirsch JE. An index to quantify an individual's scientific research output. "
        "Proc Natl Acad Sci U S A. 2005;102(46):16569-16572. doi:10.1073/pnas.0507655102"
    ),
    "callon1991": (
        "Callon M, Courtial JP, Laville F. Co-word analysis as a tool for describing the "
        "network of interactions between basic and technological research: the case of "
        "polymer chemistry. Scientometrics. 1991;22(1):155-205. doi:10.1007/BF02019280"
    ),
}

INST_COUNTRY = {
    "Xinjiang Medical University": "China",
    "Sichuan University": "China",
    "University of Franche-Comte / CHU Besancon": "France",
    "Qinghai University": "China",
    "Ulm University": "Germany",
    "University of Bern": "Switzerland",
    "Qinghai Provincial People's Hospital": "China",
    "Ataturk University": "Turkey",
    "University of Zurich": "Switzerland",
    "Medical University of Warsaw": "Poland",
}


def load(path):
    return [parse_fields(r)[0] for r in parse_wos_records(path)]


def tc_of(d):
    return int(d["TC"][0].strip()) if d.get("TC") and d["TC"][0].strip().isdigit() else 0


def py_of(d):
    return int(d["PY"][0].strip())


def phase_of(year):
    if year <= 2009:
        return 0
    if year <= 2018:
        return 1
    return 2


def is_review(d):
    return "Review" in " ".join(d.get("DT", []))


def pct(num, den):
    return f"{100.0 * num / den:.1f}"


def compute(records):
    n = len(records)
    tcs = [tc_of(d) for d in records]
    reviews = [tc_of(d) for d in records if is_review(d)]
    articles = [tc_of(d) for d in records if not is_review(d)]
    crs = {x.strip() for d in records for x in d.get("CR", []) if x.strip()}
    year_n = Counter(py_of(d) for d in records)
    year_tc = Counter()
    for d in records:
        year_tc[py_of(d)] += tc_of(d)

    country_pubs, country_cites = Counter(), defaultdict(list)
    inst_pubs, inst_cites = Counter(), defaultdict(list)
    author_pubs, author_cites = Counter(), defaultdict(list)
    journal_pubs, journal_cites = Counter(), defaultdict(list)
    author_kw = Counter()
    edges = Counter()
    n_authors_per = []
    intl = 0
    china_phase = [0, 0, 0]
    phase_n = [0, 0, 0]
    china_intl = 0
    kept_without_ae = 0
    france_big = []

    kw_counts, kw_years, kw_edges = Counter(), defaultdict(list), Counter()
    theme_phase = {name: [0, 0, 0] for name in THEMES}

    for d in records:
        year, cites = py_of(d), tc_of(d)
        p = phase_of(year)
        phase_n[p] += 1
        countries, insts = extract_countries_and_insts(d)
        insts = {i for i in insts if i != "Univ Hosp"}
        for c in countries:
            country_pubs[c] += 1
            country_cites[c].append(cites)
        for a, b in combinations(sorted(countries), 2):
            edges[(a, b)] += 1
        if len(countries) >= 2:
            intl += 1
        if "China" in countries:
            china_phase[p] += 1
            if len(countries) >= 2:
                china_intl += 1
        if "France" in countries and cites >= 500:
            france_big.append((cites, year, d["AU"][0], clean_html_entities(" ".join(d["TI"]))))
        for inst in insts:
            inst_pubs[inst] += 1
            inst_cites[inst].append(cites)
        afs = {x.strip() for x in d.get("AF", []) if x.strip() and x.strip() != "[Anonymous]"}
        n_authors_per.append(len(afs))
        for a in afs:
            author_pubs[a] += 1
            author_cites[a].append(cites)
        so = " ".join(d.get("SO", [])).strip()
        if so:
            journal_pubs[so] += 1
            journal_cites[so].append(cites)
        if d.get("DE"):
            author_kw.update(x.strip().lower() for x in " ".join(d["DE"]).split(";") if x.strip())
        blob = clean_html_entities(" ".join(d.get("TI", []) + d.get("AB", []) + d.get("DE", [])))
        if not AE_PAT.search(blob):
            kept_without_ae += 1
        kws = record_keywords(d)
        for k in kws:
            kw_counts[k] += 1
            kw_years[k].append(year)
        for a, b in combinations(sorted(kws), 2):
            kw_edges[(a, b)] += 1
        for name, theme in THEMES.items():
            if kws & theme["terms"]:
                theme_phase[name][p] += 1

    callon = compute_callon_metrics(kw_counts, kw_edges)
    ranked = journal_pubs.most_common()
    cum = []
    running = 0
    for _, count in ranked:
        running += count
        cum.append(running)
    z1 = int(next(i for i, v in enumerate(cum) if v >= n / 3.0)) + 1
    z2 = int(next(i for i, v in enumerate(cum) if v >= 2 * n / 3.0)) + 1
    # Match the figure, which uses np.searchsorted on the same cumulative sums.
    import numpy as np
    z1_fig = int(np.searchsorted(np.array(cum), n / 3.0) + 1)
    z2_fig = int(np.searchsorted(np.array(cum), 2 * n / 3.0) + 1)
    if (z1, z2) != (z1_fig, z2_fig):
        raise SystemExit(f"Bradford cut mismatch: {(z1, z2)} vs {(z1_fig, z2_fig)}")

    def entity_row(name, count, cites):
        ordered = sorted(cites)
        return {
            "name": name,
            "n": count,
            "pct": pct(count, n),
            "tc": sum(cites),
            "cpp": f"{sum(cites) / count:.2f}",
            "median": ordered[len(ordered) // 2],
            "h": calc_h_index(cites),
        }

    countries = []
    for name, count in country_pubs.most_common(12):
        row = entity_row(name, count, country_cites[name])
        below = [c for c in country_cites[name] if c < 500]
        row["cpp_below500"] = f"{sum(below) / len(below):.2f}" if below else "—"
        row["n_below500"] = len(below)
        countries.append(row)

    inst_rows = []
    for name, count in inst_pubs.most_common(15):
        if name in {"Univ Hosp", "World Health Organization"}:
            continue
        row = entity_row(name, count, inst_cites[name])
        row["country"] = INST_COUNTRY.get(name, "—")
        inst_rows.append(row)
        if len(inst_rows) == 10:
            break

    author_rows = []
    for name, count in author_pubs.most_common(12):
        author_rows.append(entity_row(name, count, author_cites[name]))

    journal_rows = []
    for name, count in journal_pubs.most_common(10):
        row = entity_row(name, count, journal_cites[name])
        row["name"] = JOURNAL_ABBR.get(name, name.title())
        journal_rows.append(row)

    theme_ids = {
        "ELRA & vascular reconstruction": "elra",
        "Hepatectomy & postoperative outcomes": "hep",
        "Liver transplantation & recurrence": "ltx",
        "Staging & imaging": "stage",
        "Antiparasitic therapy": "abz",
        "Minimally invasive & interventional": "mis",
    }
    themes = {}
    for name, counts in theme_phase.items():
        themes[theme_ids[name]] = {
            "name": name,
            "n": sum(counts),
            "p1": counts[0], "p2": counts[1], "p3": counts[2],
            "s1": pct(counts[0], phase_n[0]),
            "s2": pct(counts[1], phase_n[1]),
            "s3": pct(counts[2], phase_n[2]),
            "c": f"{callon[name][0]:.2f}",
            "d": f"{callon[name][1]:.2f}",
        }
    cents = sorted(callon[name][0] for name in THEMES)
    dens = sorted(callon[name][1] for name in THEMES)
    med_c = (cents[2] + cents[3]) / 2
    med_d = (dens[2] + dens[3]) / 2

    def apy(term):
        return sum(kw_years[term]) / len(kw_years[term])

    bursts = list(csv.DictReader(open(os.path.join(SRC, "fig7_keyword_bursts.csv"), encoding="utf-8")))
    by_kw = {row["Keyword"]: row for row in bursts}
    for kw, strength, begin, end, freq in (
        ("hepatectomy", "16.33", "2016", "2026", "71"),
        ("vascular reconstruction", "11.9", "2018", "2026", "21"),
        ("ex vivo liver resection and autotransplantation", "11.66", "2018", "2026", "45"),
        ("albendazole", "9.79", "2002", "2013", "43"),
    ):
        row = by_kw[kw]
        if (row["Burst_Strength"], row["Begin_Year"], row["End_Year"], row["Total_Frequency"]) != (strength, begin, end, freq):
            raise SystemExit(f"Burst CSV drift for {kw}: {row}")
    heat = {row["Modality"]: row for row in csv.DictReader(open(os.path.join(SRC, "fig7b_modality_heatmap.csv"), encoding="utf-8"))}
    period_cols = ["2000–05", "2006–10", "2011–15", "2016–20", "2021–26"]
    expected_heat = {
        "Hepatectomy": ["0", "1", "5", "25", "45"],
        "ELRA": ["0", "0", "3", "15", "27"],
        "Laparoscopic / robotic": ["1", "0", "0", "1", "9"],
    }
    for name, expected in expected_heat.items():
        got = [heat[name][col] for col in period_cols]
        if got != expected:
            raise SystemExit(f"Heatmap drift for {name}: {got}")

    callon_csv = list(csv.DictReader(open(os.path.join(SRC, "fig6_theme_callon_metrics.csv"), encoding="utf-8")))
    for row in callon_csv:
        got = callon[row["Theme"]]
        if abs(got[0] - float(row["Callon_Centrality"])) > 0.02 or abs(got[1] - float(row["Callon_Density"])) > 0.02:
            raise SystemExit(f"Callon drift for {row['Theme']}: {got} vs {row}")

    france_big.sort(reverse=True)
    return {
        "n": n,
        "tc": f"{sum(tcs):,}",
        "tc_raw": sum(tcs),
        "cpp": f"{sum(tcs) / n:.2f}",
        "h": calc_h_index(tcs),
        "n_cr": f"{len(crs):,}",
        "n_articles": len(articles),
        "n_reviews": len(reviews),
        "pct_articles": pct(len(articles), n),
        "pct_reviews": pct(len(reviews), n),
        "article_cpp": f"{sum(articles) / len(articles):.1f}",
        "review_cpp": f"{sum(reviews) / len(reviews):.1f}",
        "n_authors": f"{len(author_pubs):,}",
        "mean_authors": f"{sum(n_authors_per) / n:.2f}",
        "n_countries": len(country_pubs),
        "n_inst": len(inst_pubs),
        "n_de": len(author_kw),
        "kept_without_ae": kept_without_ae,
        "intl": intl,
        "intl_pct": pct(intl, n),
        "china_intl": china_intl,
        "china_intl_pct": pct(china_intl, country_pubs["China"]),
        "p1n": phase_n[0], "p2n": phase_n[1], "p3n": phase_n[2],
        "p1rate": f"{phase_n[0] / 10:.1f}",
        "p2rate": f"{phase_n[1] / 9:.1f}",
        "p3rate": f"{phase_n[2] / 8:.1f}",
        "p3pct": pct(phase_n[2], n),
        "c1": china_phase[0], "c2": china_phase[1], "c3": china_phase[2],
        "c1s": pct(china_phase[0], phase_n[0]),
        "c2s": pct(china_phase[1], phase_n[1]),
        "c3s": pct(china_phase[2], phase_n[2]),
        "y2003n": year_n[2003], "y2003tc": f"{year_tc[2003]:,}",
        "y2010n": year_n[2010], "y2010tc": f"{year_tc[2010]:,}",
        "y2019n": year_n[2019], "y2019tc": f"{year_tc[2019]:,}",
        "y2021": year_n[2021], "y2026": year_n[2026],
        "n_journals": len(journal_pubs),
        "z1j": z1, "z1p": cum[z1 - 1],
        "z2j": z2 - z1, "z2p": cum[z2 - 1] - cum[z1 - 1],
        "z3j": len(ranked) - z2, "z3p": n - cum[z2 - 1],
        "countries": countries,
        "inst": inst_rows,
        "authors": author_rows,
        "journals": journal_rows,
        "themes": themes,
        "med_c": f"{med_c:.2f}",
        "med_d": f"{med_d:.2f}",
        "apy": {k: f"{apy(k):.1f}" for k in (
            "antiparasitic therapy", "albendazole", "pet/ct", "hepatectomy",
            "ex vivo liver resection and autotransplantation", "vascular reconstruction",
            "liver transplantation", "classification",
        )},
        "bursts": bursts,
        "edges": edges.most_common(5),
        "france_big": france_big,
        "py": f"{sys.version.split()[0]}",
        "mpl": matplotlib.__version__,
        "nx": networkx.__version__,
    }


def lookup_records(records):
    by_doi = {}
    for d in records:
        doi = " ".join(d.get("DI", [])).strip().lower()
        if doi:
            by_doi.setdefault(doi, d)
    return by_doi


def format_authors(authors, doi):
    people = []
    for author in authors:
        if "," in author:
            last, rest = author.split(",", 1)
            initials = "".join(part for part in rest.replace(".", " ").split())
            people.append(f"{last.strip()} {initials}")
        else:
            people.append(author.strip())
    if len(people) > 6 or doi.lower() in FORCE_ET_AL:
        return ", ".join(people[:6]) + ", et al"
    return ", ".join(people)


def format_record(d, doi):
    title = re.sub(r"\s+", " ", clean_html_entities(" ".join(d["TI"]))).replace("::", ":").strip().rstrip(".")
    so = " ".join(d["SO"]).strip().upper()
    journal = BOOK_SERIES.get(doi.lower(), JOURNAL_ABBR.get(so))
    if journal is None:
        raise SystemExit(f"No journal abbreviation for {so}")
    volume = " ".join(d.get("VL", [])).strip()
    bp = " ".join(d.get("BP", [])).strip()
    ep = " ".join(d.get("EP", [])).strip()
    ar = " ".join(d.get("AR", [])).strip()
    if ar:
        pages = ar
    elif bp and ep and ep not in {"+", "-"}:
        pages = f"{bp}-{ep}"
    else:
        pages = bp
    locator = f"{volume}:{pages}" if pages else volume
    return (
        f"{format_authors(d['AU'], doi)}. {title}. {journal}. {d['PY'][0]};{locator}. "
        f"doi:{doi}"
    )


class Citer:
    def __init__(self, by_doi):
        self.by_doi = by_doi
        self.order = []

    def nums(self, keys):
        out = []
        for key in keys:
            canon = key if key in EXTERNAL_REFS else key.lower()
            if canon not in self.order:
                if canon not in EXTERNAL_REFS and canon not in self.by_doi:
                    raise SystemExit(f"Unresolved reference {key}")
                self.order.append(canon)
            out.append(self.order.index(canon) + 1)
        return sorted(set(out))

    @staticmethod
    def render(nums):
        if not nums:
            return ""
        chunks = []
        start = prev = nums[0]
        for num in nums[1:]:
            if num == prev + 1:
                prev = num
                continue
            chunks.append(Citer._chunk(start, prev))
            start = prev = num
        chunks.append(Citer._chunk(start, prev))
        return ",".join(chunks)

    @staticmethod
    def _chunk(start, prev):
        if start == prev:
            return str(start)
        if prev == start + 1:
            return f"{start},{prev}"
        return f"{start}-{prev}"

    def bibliography(self):
        lines = []
        for key in self.order:
            if key in EXTERNAL_REFS:
                lines.append(EXTERNAL_REFS[key])
            else:
                record = self.by_doi[key]
                doi = " ".join(record.get("DI", [])).strip()
                lines.append(format_record(record, doi))
        return lines


def fill(text, stats):
    def repl(match):
        cur = stats
        for part in match.group(1).split("."):
            cur = cur[int(part)] if part.isdigit() else cur[part]
        return str(cur)
    return re.sub(r"\{([^{}]+)\}", repl, text)


def font_run(run, size, bold=False, italic=False, color=None):
    run.bold = bold
    run.italic = italic
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = color
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    run._element.rPr.rFonts.set(qn("w:ascii"), "Times New Roman")
    run._element.rPr.rFonts.set(qn("w:hAnsi"), "Times New Roman")


def add_page_number(paragraph):
    run = paragraph.add_run()
    font_run(run, 10)
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)


def shade_header(cell):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "0")
    bottom.set(qn("w:color"), "000000")
    borders.append(bottom)
    tcPr.append(borders)


def set_table_borders(table):
    tbl = table._tbl
    tblPr = tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("left", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "nil")
        borders.append(el)
    for edge, sz in (("top", "12"), ("bottom", "12")):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), sz)
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "000000")
        borders.append(el)
    tblPr.append(borders)


def prevent_row_split(row):
    tr = row._tr
    trPr = tr.get_or_add_trPr()
    cant = OxmlElement("w:cantSplit")
    trPr.append(cant)


def add_table(doc, caption, headers, rows, widths):
    cap = doc.add_paragraph()
    cap.paragraph_format.space_before = Pt(10)
    cap.paragraph_format.space_after = Pt(4)
    cap.paragraph_format.line_spacing = 1.15
    cap.paragraph_format.first_line_indent = Inches(0)
    run = cap.add_run(caption)
    font_run(run, 10.5, bold=True)
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.autofit = False
    set_table_borders(table)
    for i, header in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.space_before = Pt(0)
        run = p.add_run(header)
        font_run(run, 9, bold=True)
        shade_header(cell)
        cell.width = Inches(widths[i])
    prevent_row_split(table.rows[0])
    for r, row in enumerate(rows):
        prevent_row_split(table.rows[r + 1])
        for c, value in enumerate(row):
            cell = table.rows[r + 1].cells[c]
            cell.text = ""
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if c else WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.space_before = Pt(0)
            run = p.add_run(str(value))
            font_run(run, 9)
            cell.width = Inches(widths[c])
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return caption


def add_rich(doc, text, citer, stats, *, kind="p"):
    text = fill(text, stats)
    if kind == "h1":
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(14)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.line_spacing = 1.15
        p.paragraph_format.first_line_indent = Inches(0)
        run = p.add_run(text)
        font_run(run, 14, bold=True)
        return text
    if kind == "h2":
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.15
        p.paragraph_format.first_line_indent = Inches(0)
        run = p.add_run(text)
        font_run(run, 12, bold=True)
        return text
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.5
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.space_before = Pt(0)
    note = kind == "note"
    p.paragraph_format.first_line_indent = Inches(0) if note or kind == "legend" else Inches(0.3)
    if kind == "center":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Inches(0)
    size = 10.5 if kind == "legend" else 12
    color = RGBColor(0x8B, 0x1E, 0x1E) if note else None
    parts = re.split(r"\[\[([^\]]+)\]\]", text)
    for i, part in enumerate(parts):
        if i % 2 == 0:
            if part:
                run = p.add_run(part)
                font_run(run, size, italic=note, color=color)
        else:
            keys = [k.strip() for k in part.split("|")]
            label = Citer.render(citer.nums(keys))
            run = p.add_run(label)
            font_run(run, size, color=color)
            run.font.superscript = True
    return text


def configure(doc):
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.different_first_page_header_footer = True
    section.header.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = section.header.paragraphs[0].add_run(
        "Bibliometrics of surgery for hepatic alveolar echinococcosis"
    )
    font_run(run, 9, italic=True)
    section.first_page_header.paragraphs[0].text = ""
    for footer in (section.footer, section.first_page_footer):
        footer.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        add_page_number(footer.paragraphs[0])
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(12)
    normal._element.rPr.rFonts.set(qn("w:ascii"), "Times New Roman")
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), "Times New Roman")


def burst_label(keyword):
    names = {
        "ex vivo liver resection and autotransplantation": "ELRA",
        "living donor liver transplantation": "Living-donor liver transplantation",
        "hepatic alveolar echinococcosis": "Hepatic alveolar echinococcosis",
        "echinococcus multilocularis": "Echinococcus multilocularis",
        "postoperative complications": "Postoperative complications",
        "vascular reconstruction": "Vascular reconstruction",
        "antiparasitic therapy": "Antiparasitic therapy",
        "inferior vena cava": "Inferior vena cava",
        "clinical features": "Clinical features",
        "hydatid disease": "Hydatid disease",
        "pet/ct": "PET/CT",
    }
    return names.get(keyword, keyword[:1].upper() + keyword[1:])


def build():
    strict = load(STRICT)
    full = load(FULL)
    stats = compute(strict)
    if stats["n"] != 362 or stats["p2rate"] != "11.6" or stats["n_articles"] != 302:
        raise SystemExit(f"Unexpected corpus stats: {stats['n']} {stats['p2rate']} {stats['n_articles']}")
    if stats["countries"][4]["name"] != "France" or stats["countries"][11]["name"] != "Italy":
        raise SystemExit(f"Country order changed: {stats['countries'][4]['name']} {stats['countries'][11]['name']}")
    if not stats["authors"][11]["name"].startswith("Kern") or not stats["inst"][2]["name"].startswith("University of Franche"):
        raise SystemExit("Author or institution order changed")
    if stats["journals"][6]["name"] != "Acta Trop" or stats["journals"][2]["n"] != stats["journals"][3]["n"]:
        raise SystemExit(f"Journal order changed: {stats['journals']}")
    if len(stats["france_big"]) != 2:
        raise SystemExit(f"Expected two highly cited French-address papers, got {stats['france_big']}")
    if stats["z1j"] != 16 or stats["n_journals"] != 169 or stats["kept_without_ae"] < 0:
        raise SystemExit("Unexpected Bradford or exception count")
    citer = Citer(lookup_records(full))
    doc = Document()
    configure(doc)
    md = []

    def emit(kind, text):
        plain = add_rich(doc, text, citer, stats, kind=kind)
        if kind == "h1":
            md.append("\n## " + fill(text, stats) + "\n")
        elif kind == "h2":
            md.append("\n### " + fill(text, stats) + "\n")
        else:
            rendered = fill(text, stats)
            def sub(match):
                keys = [k.strip() for k in match.group(1).split("|")]
                return "[" + Citer.render(citer.nums(keys)) + "]"
            # nums() above would double-register if called twice.
            # Markdown is filled after Word, so registration already happened.
            # Re-render from the same order without appending: use a dry lookup.
            md.append(plain_with_existing_numbers(text, stats, citer) + "\n")
        return plain

    def emit_table(caption, headers, rows, widths):
        add_table(doc, fill(caption, stats), headers, rows, widths)
        md.append("\n**" + fill(caption, stats) + "**\n")
        md.append("| " + " | ".join(headers) + " |\n")
        md.append("| " + " | ".join("---" for _ in headers) + " |\n")
        for row in rows:
            md.append("| " + " | ".join(str(x) for x in row) + " |\n")
        md.append("\n")

    # Title page
    add_rich(doc, "Surgical publication on hepatic alveolar echinococcosis, 2000–2026: output, collaboration, and a shift toward hepatectomy and ex vivo autotransplantation", citer, stats, kind="center")
    doc.paragraphs[-1].runs[0].bold = True
    doc.paragraphs[-1].runs[0].font.size = Pt(16)
    md.append("# Surgical publication on hepatic alveolar echinococcosis, 2000–2026: output, collaboration, and a shift toward hepatectomy and ex vivo autotransplantation\n")
    emit("center", "Running title: Bibliometrics of surgery for hepatic alveolar echinococcosis")
    emit("note", "[Author input needed: author names in final order; affiliations; equal-contribution notes; corresponding author, postal address, email and ORCID.]")
    emit("center", "Article type: original research (bibliometric analysis). Target journal: not yet chosen.")
    emit("p", "Word counts are filled after the draft is assembled and printed on the title page of the Word file by the builder.")

    emit("h1", "Abstract")
    emit("p", "Background. Hepatic alveolar echinococcosis is treated by radical hepatectomy when resection is feasible, by long-term benzimidazoles when it is not, and, for selected end-stage disease, by liver transplantation or ex vivo liver resection and autotransplantation (ELRA). This study describes the English-language surgical publication record of that disease from 2000 through 31 October 2026. It does not estimate incidence, operative volume or survival.")
    emit("p", "Methods. One Web of Science Core Collection export dated 31 October 2026 (456 English-language articles and reviews; publication years 2000–2026; full record and cited references) was screened with a PRISMA 2020 flow adapted to bibliometric eligibility. Three retracted records and 91 ineligible records were removed. In the remaining {n} papers we harmonised authors, institutions, countries and keywords, then summarised output, citations, co-authorship, Bradford journal zones, co-citation, six prespecified keyword themes, Callon centrality and density, and a windowed log-likelihood burst screen of 20 prespecified terms.")
    emit("p", "Results. The {n} papers received {tc} citations (mean {cpp} per paper; h-index {h}) and cited {n_cr} distinct reference strings. Mean annual output was {p1rate} papers per year in 2000–2009, {p2rate} in 2010–2018 and {p3rate} in 2019–2026, and {p3n} papers ({p3pct}%) were published from 2019 onward. China contributed {countries.0.n} papers ({countries.0.pct}%). Among countries with at least 30 papers, France had the highest mean citations per paper ({countries.4.cpp}); after papers with 500 or more citations were removed, that figure was {countries.4.cpp_below500} and France still ranked first in this group. The share of papers using an antiparasitic-therapy theme fell from {themes.abz.s1}% to {themes.abz.s3}%, while the hepatectomy theme rose from {themes.hep.s1}% to {themes.hep.s3}% and the ELRA/vascular theme from {themes.elra.s1}% to {themes.elra.s3}%. The strongest bursts were hepatectomy (16.33; 2016–2026), vascular reconstruction (11.90; 2018–2026) and ELRA (11.66; 2018–2026).")
    emit("p", "Conclusions. Later years of this indexed corpus contain more papers and a higher share of hepatectomy, ELRA and vascular-reconstruction terms. Those are properties of keywords, addresses and citation counts. They are not measures of operative quality or disease burden.")
    emit("p", "Keywords: alveolar echinococcosis; hepatectomy; liver transplantation; ex vivo liver resection and autotransplantation; bibliometrics; inferior vena cava")

    emit("h1", "1. Introduction")
    emit("p", "Hepatic alveolar echinococcosis, caused by the larval stage of Echinococcus multilocularis, infiltrates liver parenchyma and the hepatic vasculature and bile ducts. The WHO-Informal Working Group on Echinococcosis consensus distinguishes it from cystic echinococcosis and sets the PNM stage together with the principles of diagnosis and treatment[[10.1016/j.actatropica.2009.11.001]]. Reviews of the parasite and of the clinical disease describe radical resection as the intervention associated with durable control when a complete resection can be done, and long-term benzimidazoles when it cannot[[10.1128/CMR.00075-18|10.1016/bs.apar.2016.09.006|10.1097/QCO.0b013e32833d7516]]. In Switzerland, population survival improved markedly over the decades in which diagnosis and benzimidazole treatment became systematic[[10.1016/j.jhep.2008.03.023]]. European public-health accounts treat the infection as an expanding zoonosis rather than a historical curiosity[[10.1016/j.pt.2015.06.001]].")
    emit("p", "The surgical literature records several responses to disease that cannot be removed by a conventional hepatectomy. A 25-year prospective series compared benzimidazoles alone, curative resection plus adjuvant benzimidazoles, and palliative procedures[[10.1002/bjs.4998]]. A single-centre series from eastern France had already described the long course of 117 patients[[10.1097/00042737-200012030-00011]]. For otherwise incurable hepatic disease, a 45-patient European collaborative report evaluated allogeneic liver transplantation[[10.1097/01.TP.0000054230.63568.79]]. ELRA, complete removal of the liver with bench resection and reimplantation of the remnant, was then reported for end-stage hepatic alveolar echinococcosis with vascular invasion[[10.3760/cma.j.issn.0366-6999.2011.18.003|10.1016/j.jhep.2018.07.006]]. Interventional and surgical choices were summarised for clinicians in 2016[[10.1080/14787210.2016.1240030]].")
    emit("p", "Publication counts do not substitute for those clinical series. They do show where surgical experience is being written down, which operations enter the indexed vocabulary, and which papers the field still cites. Two recent bibliometric analyses sit next to this question without answering it. Li and colleagues mapped hepatic echinococcosis across four decades, combining cystic and alveolar disease and medical with surgical work[[10.1097/JS9.0000000000001319]]. Abulaiti and colleagues mapped digestive-system autotransplantation, a technique used for several tumours as well as for alveolar echinococcosis[[10.3389/fmed.2025.1537446]]. Neither corpus was restricted to human hepatic alveolar disease with a surgical, transplant or interventional focus, and neither states that retracted records were removed before counting.")
    emit("p", "We therefore analysed an English-language, surgery-oriented hepatic alveolar echinococcosis corpus with publication years 2000 through 2026, exported on 31 October 2026. We asked four descriptive questions. How did annual output and citations change? Which countries, institutions and authors account for the papers? Which references are co-cited? Which operative and medical themes became more or less common in the keyword record? The answers describe the indexed literature. They do not estimate incidence, the proportion of patients who undergo resection, or survival.")

    emit("h1", "2. Methods")
    emit("h2", "2.1 Source and retrieval")
    emit("p", "On 31 October 2026 a single plain-text export was taken from the Web of Science Core Collection (Clarivate; full record and cited references; file label VR 1.0). All 456 records are tagged as English, have publication years 2000–2026, and carry the export date 31 October 2026 in the DA field. Document types were articles and reviews, including the dual types proceedings paper, early access and book chapter as assigned by Web of Science. The plain-text export does not store the topic-search string, the edition list, or the exact field tags.")
    emit("note", "[Author input needed: paste the saved Web of Science search history before submission. Include the edition (Science Citation Index Expanded and any other edition), the exact TS/TI/AB/AK string, language and document-type limits, and the timespan as entered. Until that string is inserted, the counts below can be reproduced from the deposited export plus the screening rules, not by re-running a search.]")
    emit("h2", "2.2 Eligibility")
    emit("p", "Screening followed the PRISMA 2020 items for identification, screening, eligibility and inclusion[[page2021]]. The flow is a bibliometric eligibility flow: we did not assess risk of bias and we did not pool clinical outcomes. A record was excluded if Web of Science typed it as retracted or the title was marked retracted or withdrawn (n = 3; accession numbers WOS:000246982200023, WOS:000401125000020 and WOS:000507597800009). A record was excluded if the title matched a pre-specified veterinary or preclinical pattern covering dogs, sheep, primates, mice, rats, or named in-vitro antiparasitic experiments (n = 31). Fourteen accession numbers were pre-specified as exclusively extrahepatic (lung, spleen, adrenal, heart, brain or parotid) or as non-surgical allergy or nephrology, and those records were excluded. A further record was excluded if the title, abstract and author keywords contained none of a pre-specified alveolar expression (alveolar echinococcosis or hydatid, Echinococcus multilocularis, multilocular echinococcosis, Echinococcus alveolaris, alveococcosis, or the token HAE). Seven accession numbers were exempt from that expression rule because they are landmark papers on ex vivo liver surgery, vena cava reconstruction with major hepatectomy, or hepatic echinococcosis surgery that the export contained without the expression. Keywords Plus alone was not accepted as evidence of an alveolar topic. Reviews, case reports and small series were not excluded for those reasons. The strict corpus contains {n} records. The 453 non-retracted records were kept only as a sensitivity file and are not the denominator of the results.")
    emit("p", "Rules were applied by one script. There was no second clinical reviewer. Boundary decisions are therefore the coded rules and the two accession-number lists, which travel with the code. {kept_without_ae} included records do not themselves match the alveolar expression and are present because of the seven-item exemption list. A preclinical paper whose title did not match the veterinary pattern could remain. An extrahepatic paper that was not on the fourteen-item list could remain if the expression was present.")
    emit("h2", "2.3 Harmonisation")
    emit("p", "Four thesauri were applied before counting. Author names join inverted and unpunctuated forms to one canonical name, including Wen H, Aji T and Ran B. Institutions are read from the first segment of each C1 address and from C3 enhanced organisations, and affiliated hospitals are folded into the parent university used in this study (West China Hospital with Sichuan University; affiliated hospitals of Xinjiang Medical University with that university; CHU Besançon with the University of Franche-Comté). Countries are the last segment of C1, with Peoples R China mapped to China, UK constituent countries to the United Kingdom, and Türkiye to Turkey. Author keywords and Keywords Plus were lower-cased and passed through a synonym list so that spelling variants of ELRA, radical resection and classification meet. Residual synonyms remain. Counts of authors, institutions and countries below are counts after this mapping, not counts of raw strings. A paper is credited to every country and institution on its addresses (full counting). An international paper is one with at least two countries on C1.")
    emit("h2", "2.4 Indicators")
    emit("p", "Citations are Web of Science Times Cited on the export date. Papers from 2024–2026 have had little time to be cited, so recent productivity is not comparable with earlier citation totals. Citations per paper are Times Cited divided by the number of papers. The h-index of a set is the largest h such that h papers in the set have at least h citations[[hirsch2005]]. Co-authorship links count each paper once for every pair of countries, institutions or authors on that paper. Median citations are reported beside means because means are pulled by consensus and review articles.")
    emit("p", "For the Bradford partition, journals were ordered by decreasing paper count. Zone 1 is the shortest prefix of that list whose papers reach one third of {n}. Zone 2 continues until two thirds. Zone 3 is the remainder. Co-citation frequency is the number of the {n} bibliographies that contain a given cited-reference string. Reference strings were not disambiguated: one work split across two Web of Science strings is counted twice.")
    emit("p", "Keyword analyses use the union of author keywords and Keywords Plus after the thesaurus, counted once per paper. The average publication year of a term is the arithmetic mean of the publication years of papers that carry it. Six themes were specified before plotting, as term sets. A paper is counted in a theme if it carries at least one term from that set. Generic disease names, including alveolar echinococcosis, Echinococcus multilocularis, liver and disease, were left out of every set so that theme membership would not collapse toward the whole corpus. The sets are ELRA and vascular reconstruction; hepatectomy and postoperative outcomes; liver transplantation and recurrence; staging and imaging; antiparasitic therapy; and minimally invasive or interventional procedures. The term lists are those in the figure code and in source_data/fig6_theme_callon_metrics.csv. Phases were fixed as 2000–2009, 2010–2018 and 2019–2026 (10, 9 and 8 years). They are descriptive bins, not estimated change points. The year 2026 stops at the export date.")
    emit("p", "Callon centrality and density used keywords occurring at least three times. The equivalence index of two keywords is eij = cij squared, divided by ci times cj, where cij is the number of papers listing both and ci is the frequency of keyword i[[callon1991]]. Centrality of a theme is 10 times the sum of eij over pairs with one keyword inside the theme and one outside. Density is 100 times the sum of eij over pairs inside the theme, divided by the number of theme keywords that passed the frequency threshold. Quadrant labels use the median centrality and the median density of these six themes. The diagram is a description of six prespecified themes, not a clustering solution.")
    emit("p", "For each of 20 prespecified clinical keywords, every window of 2 to 12 years within 2000–2026 in which the keyword occurred in both the first and the last year was scored. The score is the log-likelihood ratio of a two-proportion model (the rate inside the window against the rate in the whole corpus) and is set to zero when the inside rate does not exceed the corpus rate. We report the window with the largest score. The 20 terms were chosen. They are not the top 20 terms from an all-keyword ranking. The score is not a Kleinberg burst weight, and it is not a burst weight from CiteSpace.")
    emit("h2", "2.5 Software and display")
    emit("p", "Cleaning and statistics used Python {py}. Figures were drawn with Matplotlib {mpl} and NetworkX {nx}. Networks in the figures are radial diagrams of the top nodes, with edges inside the circle and labels outside it. They are not force-directed VOSviewer layouts. Thesaurus files were also written in a two-column form that VOSviewer can import, so a reader can redraw the maps. A language model assisted the code and the prose. Every count in the results was recomputed from the export by the scripts in this project. No numerical result was accepted from the model without that recomputation.")

    emit("h1", "3. Results")
    emit("h2", "3.1 The corpus")
    emit("p", "Of 456 exported records, 3 were retracted and 91 failed eligibility (46 with no alveolar expression in the title, abstract or author keywords, 31 veterinary or preclinical, and 14 exclusively extrahepatic). The strict corpus contains {n} records (Figure 1). Of these, {n_articles} ({pct_articles}%) are articles, including those also typed as proceedings papers or early access, and {n_reviews} ({pct_reviews}%) are reviews, including two also typed as book chapters. The papers received {tc} citations (mean {cpp} per paper; h-index {h}) and their bibliographies contain {n_cr} distinct cited-reference strings. Reviews were cited more heavily (mean {review_cpp}) than articles (mean {article_cpp}), which is the expected direction for consensus and narrative reviews and is why citations per paper should not be read as a surgical-quality score. After name harmonisation the corpus has {n_authors} authors (mean {mean_authors} author names per paper), addresses in {n_countries} countries and {n_inst} institutions, and {n_de} distinct author-keyword strings.")

    emit("h2", "3.2 Growth across three phases")
    emit("p", "Annual output averaged {p1rate} papers per year in 2000–2009 ({p1n} papers), {p2rate} in 2010–2018 ({p2n} papers) and {p3rate} in 2019–2026 ({p3n} papers, {p3pct}% of the corpus) (Figure 2a, Table 1). The fullest calendar year in the file is 2021, with {y2021} papers. The {y2026} papers dated 2026 are a partial year ending on 31 October, so the third-phase mean is not a rate for a completed year and will change if later 2026 papers are added. Papers carrying a Chinese address were {c1} of {p1n} in the first phase ({c1s}%), {c2} of {p2n} in the second ({c2s}%) and {c3} of {p3n} in the third ({c3s}%).")
    emit("p", "Citations summed by publication year peak in 2010 ({y2010tc} citations across {y2010n} papers), 2019 ({y2019tc} across {y2019n} papers) and 2003 ({y2003tc} across {y2003n} papers) (Figure 2b). These year totals are not the citation count of a single paper. Brunetti and colleagues account for 1,617 of the 2010 total[[10.1016/j.actatropica.2009.11.001]]. Wen and colleagues account for 918 of the 2019 total[[10.1128/CMR.00075-18]]. The 2003 total is spread across {y2003n} papers. The largest three are a national review of echinococcosis in Turkey (132 citations), a review of E. multilocularis (125) and the European transplantation report (120)[[10.1097/01.TP.0000054230.63568.79]].")

    phase_rows = [
        ["I", "2000–2009", str(stats["p1n"]), stats["p1rate"], pct(stats["p1n"], stats["n"]) + "%", f"{stats['c1']} ({stats['c1s']}%)"],
        ["II", "2010–2018", str(stats["p2n"]), stats["p2rate"], pct(stats["p2n"], stats["n"]) + "%", f"{stats['c2']} ({stats['c2s']}%)"],
        ["III", "2019–2026", str(stats["p3n"]), stats["p3rate"], pct(stats["p3n"], stats["n"]) + "%", f"{stats['c3']} ({stats['c3s']}%)"],
        ["All", "2000–2026", str(stats["n"]), "—", "100%", f"{stats['countries'][0]['n']} ({stats['countries'][0]['pct']}%)"],
    ]
    emit_table(
        "Table 1. Output in three prespecified phases.",
        ["Phase", "Years", "Papers", "Papers/year", "Share of corpus", "Papers with a Chinese address"],
        phase_rows,
        [0.7, 1.1, 0.8, 1.1, 1.2, 2.2],
    )
    emit("legend", "Phase III includes a partial year, 2026, ending on the export date of 31 October 2026. A Chinese address means at least one C1 affiliation mapped to China. Shares use full counting.")

    emit("h2", "3.3 Countries and institutions")
    emit("p", "China contributed {countries.0.n} papers ({countries.0.pct}%), followed by Germany ({countries.1.n}), Switzerland ({countries.2.n}), Turkey ({countries.3.n}) and France ({countries.4.n}) (Figure 3a, Table 2). Mean citations per paper were highest for France ({countries.4.cpp}), then Germany ({countries.1.cpp}) and Switzerland ({countries.2.cpp}), and lowest among these five for China ({countries.0.cpp}). Medians were much closer together: {countries.4.median} for France, {countries.1.median} for Germany, {countries.2.median} for Switzerland, {countries.3.median} for Turkey and {countries.0.median} for China. Italy's mean of {countries.11.cpp} rests on {countries.11.n} papers and falls to {countries.11.cpp_below500} when papers with 500 or more citations are removed. Two papers with at least 500 citations carry a French address and account for the gap between the French mean of {countries.4.cpp} and the mean of {countries.4.cpp_below500} on the remaining {countries.4.n_below500} papers. France still has the highest mean of the five countries with at least 30 papers after that removal.")
    emit("p", "{intl} papers ({intl_pct}%) list at least two countries. Of {countries.0.n} papers with a Chinese address, {china_intl} ({china_intl_pct}%) also list another country. The most frequent country pairs were France–Switzerland ({edges.0.1} papers), Germany–Switzerland ({edges.1.1}), China–France ({edges.2.1}), Australia–China ({edges.3.1}) and France–Germany ({edges.4.1}) (Figure 3b). The collaboration diagram is a count of shared addresses, not a map of referral pathways.")

    country_rows = []
    for i, row in enumerate(stats["countries"][:10], 1):
        country_rows.append([str(i), row["name"], f"{row['n']} ({row['pct']}%)", f"{row['tc']:,}", row["cpp"], str(row["median"]), str(row["h"])])
    emit_table(
        "Table 2. The ten countries with the most papers.",
        ["Rank", "Country", "Papers", "Citations", "Mean", "Median", "h"],
        country_rows,
        [0.55, 1.4, 1.15, 0.95, 0.7, 0.75, 0.5],
    )
    emit("legend", "Full counting: a paper is credited to every country on its addresses, and its full Times Cited value is added to each of those countries. Mean and median are citations per paper. h is the h-index of that country's papers in this corpus.")

    emit("p", "After institutional harmonisation, Xinjiang Medical University has {inst.0.n} papers (mean citations {inst.0.cpp}; h-index {inst.0.h}), Sichuan University {inst.1.n} (mean {inst.1.cpp}), the University of Franche-Comté/CHU Besançon {inst.2.n} (mean {inst.2.cpp}; h-index {inst.2.h}), Qinghai University {inst.3.n} (mean {inst.3.cpp}), Ulm {inst.4.n} (mean {inst.4.cpp}) and Bern {inst.5.n} (mean {inst.5.cpp}) (Figure 3c and 3d, Table 3). The Chinese centres account for more papers. The Franche-Comté/Besançon and Ulm series account for more citations per paper. Qinghai University's mean of {inst.3.cpp} and the Qinghai Provincial People's Hospital mean of {inst.6.cpp} sit on more recent papers, which have had less time to be cited. Folding a hospital into its university moves counts toward the parent label; centres that were not in the thesaurus remain separate and can be under-counted.")

    inst_rows = []
    for i, row in enumerate(stats["inst"], 1):
        inst_rows.append([str(i), row["name"], row["country"], str(row["n"]), f"{row['tc']:,}", row["cpp"], str(row["h"])])
    emit_table(
        "Table 3. The ten institutions with the most papers after harmonisation.",
        ["Rank", "Institution", "Country", "Papers", "Citations", "Mean", "h"],
        inst_rows,
        [0.5, 2.7, 1.15, 0.7, 0.9, 0.65, 0.45],
    )
    emit("legend", "Affiliated hospitals listed in the thesaurus are counted with the parent university. Means are citations per paper under full counting.")

    emit("h2", "3.4 Authors and journals")
    emit("p", "The largest author counts after disambiguation are Aji T ({authors.0.n} papers), Wen H ({authors.1.n}), Shao YM ({authors.2.n}), Vuitton DA ({authors.3.n}), Wang WT ({authors.4.n}) and Jiang TM ({authors.5.n}) (Figure 4a and 4b, Table 4). Citation rate does not follow paper count. Vuitton DA has a mean of {authors.3.cpp} citations per paper and an h-index of {authors.3.h} inside this corpus; Kern P has {authors.11.n} papers, a mean of {authors.11.cpp} and an h-index of {authors.11.h}. Bresson-Hadni S has {authors.6.n} papers (mean {authors.6.cpp}). These h-indices use only this corpus and only Times Cited on the export date. They are not career h-indices. The WoS spelling Gruener is retained where the record uses it.")
    emit("p", "The {n} papers appear in {n_journals} journals (Figure 4c and 4d). World Journal of Gastroenterology published {journals.0.n} (mean citations {journals.0.cpp}), Medicine {journals.1.n} (mean {journals.1.cpp}), BMC Infectious Diseases and Pathogens {journals.2.n} each, and PLoS Neglected Tropical Diseases {journals.4.n}. Acta Tropica published {journals.6.n} papers with a mean of {journals.6.cpp}, a mean carried by the 2010 consensus. The Bradford partition places {z1p} papers in {z1j} journals (zone 1), {z2p} papers in the next {z2j} journals (zone 2) and {z3p} papers in the remaining {z3j} journals (zone 3).")

    author_rows = []
    for i, row in enumerate(stats["authors"], 1):
        author_rows.append([str(i), row["name"], str(row["n"]), f"{row['tc']:,}", row["cpp"], str(row["h"])])
    emit_table(
        "Table 4. The twelve authors with the most papers after disambiguation.",
        ["Rank", "Author (Web of Science form)", "Papers", "Citations", "Mean", "h"],
        author_rows,
        [0.55, 2.6, 0.8, 1.0, 0.8, 0.5],
    )
    emit("legend", "Each paper is counted once per harmonised author. The h-index is computed inside this 362-paper corpus only.")

    emit("h2", "3.5 Co-cited references")
    emit("p", "The cited-reference strings that appear in the most bibliographies are Brunetti and colleagues, 2010, Acta Tropica (155 papers)[[10.1016/j.actatropica.2009.11.001]]; Kern and colleagues, 2006, Parasitology International volume 55, page S283 (109 papers); Wen and colleagues, 2019, Clinical Microbiology Reviews (81)[[10.1128/CMR.00075-18]]; Bresson-Hadni and colleagues, 2000 (74)[[10.1097/00042737-200012030-00011]]; and Koch and colleagues, 2003, Transplantation (67)[[10.1097/01.TP.0000054230.63568.79]] (Figure 5). The 2006 Kern string is the PNM classification paper as recorded by Web of Science; we did not re-derive its title from a source outside this export, and we did not merge it with any later reprint. Strings for McManus and colleagues, 2003, Lancet (60) and for Deplazes and colleagues, 2017, Advances in Parasitology (56) follow. Because strings were not harmonised, these ranks are ranks of Web of Science strings, not of canonical works.")

    emit("h2", "3.6 Keyword themes and bursts")
    emit("p", "Average publication year separates earlier medical and imaging terms from later operative terms (Figure 6b). Antiparasitic therapy averages {apy.antiparasitic therapy}, albendazole {apy.albendazole}, PET/CT {apy.pet/ct} and liver transplantation {apy.liver transplantation}. Hepatectomy averages {apy.hepatectomy}, classification {apy.classification}, ELRA {apy.ex vivo liver resection and autotransplantation} and vascular reconstruction {apy.vascular reconstruction}.")
    emit("p", "Theme membership, which is keyword presence rather than a procedure count, moved in the same direction (Figure 6c). The antiparasitic theme appears in {themes.abz.p1}, {themes.abz.p2} and {themes.abz.p3} papers across the three phases ({themes.abz.s1}%, {themes.abz.s2}% and {themes.abz.s3}% of each phase). The hepatectomy theme appears in {themes.hep.p1}, {themes.hep.p2} and {themes.hep.p3} papers ({themes.hep.s1}%, {themes.hep.s2}% and {themes.hep.s3}%). The ELRA and vascular theme appears in {themes.elra.p1}, {themes.elra.p2} and {themes.elra.p3} papers ({themes.elra.s1}%, {themes.elra.s2}% and {themes.elra.s3}%). Liver-transplantation terms remain common ({themes.ltx.p1}, {themes.ltx.p2} and {themes.ltx.p3} papers) but their share of a growing corpus moves from {themes.ltx.s1}% to {themes.ltx.s3}%. The minimally invasive theme remains the smallest ({themes.mis.p1}, {themes.mis.p2} and {themes.mis.p3} papers).")
    emit("p", "On the Callon diagram the six themes have median centrality {med_c} and median density {med_d} (Figure 6d). Staging and imaging sits above both medians (centrality {themes.stage.c}, density {themes.stage.d}). ELRA and vascular reconstruction sits above the density median and below the centrality median ({themes.elra.c}, {themes.elra.d}). Liver transplantation and recurrence sits above the centrality median and below the density median ({themes.ltx.c}, {themes.ltx.d}). Hepatectomy sits above the centrality median and just below the density median ({themes.hep.c} against {med_d}). Antiparasitic therapy sits just above the density median and below the centrality median. Minimally invasive and interventional terms sit below both. With only six hand-built themes, a theme that lies close to a median would change quadrant if the term list changed. The quadrant names are labels for this split. The decline in the antiparasitic share is a statement about the phase counts, not about the quadrant.")
    emit("p", "The windowed log-likelihood screen gives the highest scores to hepatectomy (16.33, 2016–2026), vascular reconstruction (11.90, 2018–2026), ELRA (11.66, 2018–2026), postoperative complications (11.18, 2014–2024), experience (10.76, 2009–2020) and classification (10.49, 2015–2026) (Figure 7a, Table 5). Albendazole scores 9.79 for 2002–2013, an earlier window. The heatmap uses the same keyword logic in five periods (Figure 7b). Papers whose keywords meet the hepatectomy or radical-resection set number 0, 1, 5, 25 and 45 across 2000–2005, 2006–2010, 2011–2015, 2016–2020 and 2021–2026. The corresponding ELRA counts are 0, 0, 3, 15 and 27. Laparoscopic or robotic terms occur in 1, 0, 0, 1 and 9 papers. A paper can fall in more than one row, and a row counts indexed terms, not operations performed.")

    burst_rows = []
    for row in stats["bursts"]:
        burst_rows.append([
            burst_label(row["Keyword"]),
            row["Burst_Strength"],
            row["Begin_Year"],
            row["End_Year"],
            row["Total_Frequency"],
        ])
    emit_table(
        "Table 5. Highest-scoring window for each of 20 prespecified keywords.",
        ["Keyword", "Score", "Window start", "Window end", "Papers with the term"],
        burst_rows,
        [2.5, 0.7, 1.15, 1.1, 1.6],
    )
    emit("legend", "The score is a two-proportion log-likelihood ratio for the best window of 2–12 years. Terms were prespecified. The score is not a Kleinberg burst weight and not a weight from CiteSpace. Windows are sorted by start year in the source file.")

    emit("h1", "4. Discussion")
    emit("p", "In this English-language Web of Science corpus, surgical publication on hepatic alveolar echinococcosis accelerated after 2010 and again after 2018, and the later papers more often carry the keywords of hepatectomy, ELRA and vascular reconstruction. Antiparasitic terms did not disappear, but they account for a smaller share of a larger literature. That is the result the counts support.")
    emit("p", "The timing lines up with clinical series already in the corpus, without those series being re-analysed here. Long Asian resection cohorts were already in print before the hepatectomy keyword burst: a Hokkaido series of 188 patients treated from 1984 to 2009[[10.1016/j.jamcollsurg.2011.02.007]] and a western-China series of 144 hepatectomies[[10.1016/j.ijsu.2016.09.094]]. A Swiss tertiary-centre cohort described resection outcomes in an endemic region[[10.1007/s00268-015-3109-2]]. ELRA for end-stage hepatic disease was reported as a case series in 2011 and 2016[[10.3760/cma.j.issn.0366-6999.2011.18.003|10.1111/ajt.13465]], as an alternative to allotransplantation in 2018[[10.1016/j.jhep.2018.07.006]], and with technical modifications in a 31-patient series[[10.1111/ajt.14621]]. A later single-centre comparison of ELRA with allotransplantation used 35 ELRA procedures and 6 allotransplants[[10.1016/j.ijid.2018.11.016]]. A retrospective cohort of 228 patients with end-stage disease compared ELRA with non-surgical treatment[[10.1093/cid/ciac195]]. We cite these designs and sample sizes as the authors reported them. We do not import their survival estimates, and the keyword burst is not evidence that those estimates are unbiased.")
    emit("p", "The vascular-reconstruction burst has the same status. Reconstruction of the inferior vena cava during ELRA is described in a 114-patient series[[10.3748/wjg.v28.i31.4351]], material choice for that reconstruction in 91 patients[[10.1016/j.asjsur.2022.03.045]], and use of the ligamentum teres hepatis for outflow in 24 patients[[10.1016/j.surg.2021.03.040]]. Three-dimensional reconstruction for operative planning is reported in a hepatectomy series in which 59 of 106 patients had a preoperative model[[10.3748/wjg.v21.i35.10200]]. Classification terms burst from 2015, the period in which ultrasonographic and computed-tomography classifications of hepatic alveolar echinococcosis were proposed[[10.3748/wjg.v21.i43.12392|10.3748/wjg.v22.i13.3621]]. None of these keyword coincidences validates a classification or a reconstruction technique.")
    emit("p", "Minimally invasive terms remain uncommon in the index. Laparoscopic hepatectomy for hepatic alveolar echinococcosis is reported from an endemic centre and from Bern[[10.1051/parasite/2021001|10.1371/journal.pntd.0010708]]. A robotic series of posterosuperior resections included both cystic and alveolar disease, so it is not an alveolar-only cohort[[10.3748/wjg.v26.i21.2831]]. Associating liver partition and portal-vein ligation for staged hepatectomy is present as a single case report[[10.4240/wjgs.v10.i1.1]]. The heatmap counts of laparoscopic or robotic terms (nine papers in 2021–2026) match a literature that has case series, not a literature that has replaced open resection. A systematic review of ELRA that is not restricted to alveolar echinococcosis was retained in this corpus by the exemption list; its presence should not be read as an alveolar-echinococcosis meta-analysis[[10.1016/j.surg.2020.05.036]].")
    emit("p", "Two geographic patterns need a counting caveat. Paper volume is concentrated in Xinjiang, Sichuan and Qinghai and in a small set of European reference centres, which is consistent with where the clinical series above were written. Citation means are not a second copy of that map. Under full counting, a consensus or a widely cited review adds its entire Times Cited value to every country on the byline. Removing papers with 500 or more citations lowers the French mean from {countries.4.cpp} to {countries.4.cpp_below500} and the Italian mean from {countries.11.cpp} to {countries.11.cpp_below500}, and it barely changes the Chinese mean. Rankings of citations per paper in this field are rankings of a handful of reviews plus a long tail of surgical reports. International co-authorship is uncommon ({intl_pct}% of papers; {china_intl_pct}% of papers with a Chinese address). That is a statement about addresses in this index. It is not a measure of whether clinicians discuss cases across borders outside the byline.")
    emit("p", "The same boundary applies to the medical theme. Benzimidazoles remain the treatment of unresectable disease, and stopping rules based on PET/CT and serology have been studied in small prospective groups[[10.1371/journal.pntd.0003964]]. A fall in the share of papers that use the words albendazole or antiparasitic therapy can mean that later papers treat medical therapy as background and put the new surgical noun in the keyword field. It cannot mean that benzimidazoles are used in a smaller fraction of patients. Immunosuppression-associated disease is a clinical concern documented in a patient series[[10.1093/cid/ciu520]] and is not a keyword theme we specified. Recurrence after transplantation was the question of a 20-year follow-up study[[10.1002/lt.22299]]. Our transplantation theme mixes the words transplantation, recurrence, follow-up and immunosuppression, so it cannot separate a change in transplant practice from a change in follow-up vocabulary.")
    emit("p", "Several limits bound every claim above. The corpus is one database, English only, and the topic-search string was not stored in the export, so a reader cannot rebuild the 456 records from the Methods until that string is supplied. Screening was a script, not two reviewers, and the extrahepatic and landmark decisions used accession lists. Veterinary exclusion depended on the title. {kept_without_ae} included records lack the alveolar expression. Author, hospital and keyword synonyms that are not in the thesauri are still split. Citations favour older reviews and stop on 31 October 2026. Co-citation ranks unmerged reference strings. Themes, the 20 burst terms and the three phases were chosen by us; a different list would move the Callon medians, the heatmap and the phase means. Keywords Plus adds indexer terms the authors did not choose. Full counting double-credits multinational papers. Nothing in the design links a keyword to an operation actually performed, a margin, a complication or a survival time. A second database, fractional counting, or a registry of resections would be required before any of those clinical quantities could be discussed as results of this study. Overlap with the broader hepatic-echinococcosis map and with the autotransplantation map is real, and those papers remain the appropriate citations for questions wider than surgery for hepatic alveolar disease[[10.1097/JS9.0000000000001319|10.3389/fmed.2025.1537446|10.1016/j.jhep.2021.02.015]].")

    emit("h1", "5. Conclusions")
    emit("p", "From 2000 to 31 October 2026, the English-language Web of Science record of surgery for hepatic alveolar echinococcosis grew from 6.0 papers per year to 11.6 and then to 24.8, with more than half of the {n} papers published from 2019 onward. Output is concentrated in a few Chinese and European centres. Citation means are dominated by consensus and review articles under full counting. In the keyword record, hepatectomy, ELRA and vascular reconstruction occupy a larger share of later years, and antiparasitic terms a smaller share. Laparoscopic and robotic terms are still rare. These statements describe indexed publications. They do not describe how often each operation is done, or how patients fare.")

    emit("h1", "Declarations")
    emit("h2", "Ethics approval and consent to participate")
    emit("p", "This study analysed published bibliographic records and did not enrol participants. [Author input needed: confirm with the authors' institution whether a formal waiver or exemption number must be stated.]")
    emit("h2", "Consent for publication")
    emit("p", "Not applicable.")
    emit("h2", "Availability of data and materials")
    emit("p", "The Web of Science records are subject to Clarivate's licence and are not republished as a bulk download. The screening log, thesauri, aggregated tables and figure source data used to produce the counts in this draft accompany the analysis code. [Author input needed: state the repository, the accession number and the access conditions that the licence allows. Do not write that the raw export is openly available unless Clarivate's terms and the institution agree.]")
    emit("h2", "Competing interests")
    emit("note", "[Author input needed: a competing-interests statement for every author, or a confirmation that the authors declare none.]")
    emit("h2", "Funding")
    emit("note", "[Author input needed: grant names, numbers and the funder's role. If there was no specific grant, write that explicitly.]")
    emit("h2", "Authors' contributions")
    emit("note", "[Author input needed: CRediT roles. Do not leave a model-written contribution list in the submitted file.]")
    emit("h2", "Acknowledgements")
    emit("note", "[Author input needed.]")
    emit("h2", "Use of a language model")
    emit("p", "A language model assisted code for cleaning, counting and figure drawing, and assisted drafting of the English prose. The authors are responsible for the search string, the eligibility rules, the thesauri and every interpretation. Counts reported here were recomputed from the export. [Author input needed: keep, shorten or move this statement to match the target journal's policy on artificial-intelligence tools, and name the tool the journal requires.]")

    emit("h1", "References")
    # Force registration of any key not yet cited? No: only cited keys belong.
    # Bibliography must be emitted in cite order. add_rich already registered in order.
    for i, line in enumerate(citer.bibliography(), 1):
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Inches(0.3)
        p.paragraph_format.first_line_indent = Inches(-0.3)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.line_spacing = 1.15
        run = p.add_run(f"{i}. {line}")
        font_run(run, 10.5)
        md.append(f"{i}. {line}\n")

    doc.add_page_break()
    emit("h1", "Figure legends")
    legends = [
        ("Figure 1. Eligibility flow for the hepatic alveolar echinococcosis surgery corpus.",
         "The export contained 456 English-language records (articles and reviews; publication years 2000–2026; exported 31 October 2026). Three retracted records were removed. Ninety-one further records failed eligibility: 46 with no alveolar expression in the title, abstract or author keywords, 31 veterinary or preclinical records, and 14 exclusively extrahepatic records. The analysed set has 362 records (302 articles and 60 reviews), 10,361 citations, an h-index of 43 and 6,238 distinct cited-reference strings. The topic-search string is not stored in the export."),
        ("Figure 2. Annual output and citations, 2000–2026.",
         "(a) Bars are annual papers and the line is the cumulative count. Means are 6.0 papers/year in 2000–2009 (60 papers), 11.6 in 2010–2018 (104 papers) and 24.8 in 2019–2026 (198 papers). The 2026 bar ends on 31 October 2026. (b) Bars are the sum of Times Cited for papers published in that year, and the line is citations per paper. Year totals are 772 citations across 12 papers in 2003, 1,955 in 2010 (1,617 of them Brunetti et al.) and 1,145 in 2019 (918 of them Wen et al.)."),
        ("Figure 3. Countries and institutions.",
         "(a) The ten countries with the most papers, with citations per paper. (b) Co-authorship among the twelve countries with the most papers. Node area scales with paper count and line width with the number of joint papers. (c) The ten institutions with the most papers after hospital-to-university harmonisation. (d) Co-authorship among those institutions. Full counting is used throughout."),
        ("Figure 4. Authors, journals and the Bradford partition.",
         "(a) Co-authorship among the twelve authors with the most papers. (b) Annual output of the ten authors with the most papers. Marker area scales with papers in that year and colour with citations accrued by those papers. (c) The ten journals with the most papers. (d) Cumulative papers against journal rank on a log axis, for 169 journals. Zone 1 contains 16 journals and 122 papers, zone 2 contains 46 journals and 121 papers, and zone 3 contains 107 journals and 119 papers."),
        ("Figure 5. Co-cited reference strings.",
         "(a) Links among the twelve most frequent cited-reference strings. (b) The same twelve strings ranked by the number of bibliographies that contain them. Strings were not merged across variant records. Colour in the figure groups strings only as a reading aid."),
        ("Figure 6. Prespecified keyword themes.",
         "(a) Co-occurrence among twelve keywords. Colour marks a prespecified theme; grey means the keyword is in none of the six themes. (b) Average publication year. (c) Papers per phase that carry at least one term from each theme. Generic disease names were excluded from every theme. (d) Callon centrality against Callon density. Cross-hairs are the medians of the six themes. Quadrant names label that median split. They are not the output of a clustering algorithm."),
        ("Figure 7. Keyword bursts and period counts.",
         "(a) For each of 20 prespecified keywords, the window of 2–12 years with the highest two-proportion log-likelihood score. The terms were chosen, and the scores are not weights from CiteSpace. (b) Papers per period whose keywords intersect each operative or diagnostic group. Laparoscopic and robotic terms are separate from percutaneous, ablation and ERCP terms. A paper may contribute to more than one row."),
    ]
    figures = [
        "fig1_prisma_flowchart.png",
        "fig2_annual_trends.png",
        "fig3_countries_institutions.png",
        "fig4_authors_journals.png",
        "fig5_cocitation_analysis.png",
        "fig6_keyword_cooccurrence.png",
        "fig7_keyword_bursts.png",
    ]
    for (title, body), name in zip(legends, figures):
        doc.add_page_break()
        emit("h2", title)
        emit("legend", body)
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run()
        run.add_picture(os.path.join(FIG, name), width=Inches(6.3))
        md.append(f"\n### {title}\n\n{body}\n\n")

    doc.add_page_break()
    emit("h1", "REMOVE BEFORE SUBMISSION — author checklist")
    emit("note", "1. Insert the saved Web of Science search history in section 2.1 and confirm that it returns 456 records on the stated export date.")
    emit("note", "2. Complete authors, affiliations, corresponding author, ORCID, funding, competing interests, contributions and acknowledgements.")
    emit("note", "3. Confirm the institutional position on ethics review for a bibliographic study, and the journal's rule on language-model assistance.")
    emit("note", "4. Decide what may be deposited under the Web of Science licence. Do not post the raw export unless that licence allows it.")
    emit("note", "5. Choose the target journal and apply its reference style, word limit, figure format (the source files include PDF, SVG and 600 dpi TIFF) and line-number requirement.")
    emit("note", "6. Re-read every citation against the PDF, especially sample sizes attributed to other studies in the Discussion. Those sizes were taken from the abstracts in this export.")
    emit("note", "7. This page and the red placeholder paragraphs are not part of the submitted manuscript.")

    # Word counts from body paragraphs, excluding checklist by stopping at the marker.
    body_words = []
    abstract_words = []
    mode = None
    for p in doc.paragraphs:
        t = p.text.strip()
        if t.startswith("REMOVE BEFORE"):
            break
        if t == "Abstract":
            mode = "abs"
            continue
        if t.startswith("1. Introduction"):
            mode = "main"
        if t == "Declarations":
            mode = "back"
        if t == "References":
            mode = "refs"
        if mode == "abs":
            abstract_words.append(t)
        elif mode == "main":
            body_words.append(t)
    n_abs = len(re.findall(r"[A-Za-z0-9']+", " ".join(abstract_words)))
    n_main = len(re.findall(r"[A-Za-z0-9']+", " ".join(body_words)))
    # Patch the title-page sentence.
    for p in doc.paragraphs:
        if p.text.startswith("Word counts are filled"):
            for run in p.runs:
                run.text = ""
            run = p.runs[0]
            run.text = (
                f"Abstract: {n_abs} words. Main text (Introduction through Conclusions): "
                f"{n_main} words. Tables: 5. Figures: 7."
            )
            font_run(run, 12)
            break

    os.makedirs(os.path.dirname(OUT_DOCX), exist_ok=True)
    doc.save(OUT_DOCX)
    with open(OUT_MD, "w", encoding="utf-8") as handle:
        handle.write("".join(md))
    text = "\n".join(p.text for p in doc.paragraphs)
    banned = ["11.4", "6,842", "6842", "170 journal", "304 original", "unprecedented", "for the first time", "Kleinberg automaton", "CiteSpace burst"]
    found = [b for b in banned if b in text]
    if found:
        raise SystemExit(f"Banned phrases present: {found}")
    if "[[".join([]) or "[[" in text:
        raise SystemExit("Unresolved citation marker")
    if text.count("11.6") < 2 or "6,238" not in text or "302" not in text:
        raise SystemExit("Expected verified counts missing from the manuscript")
    print(f"Wrote {OUT_DOCX}")
    print(f"Abstract words: {n_abs}; main-text words: {n_main}; references: {len(citer.order)}")
    print(f"Kept without AE expression: {stats['kept_without_ae']}")
    print(f"France high-cite papers: {stats['france_big']}")


def plain_with_existing_numbers(text, stats, citer):
    """Markdown twin. Citation numbers were assigned when the Word paragraph was built."""
    rendered = fill(text, stats)
    # The Word pass already consumed the markers via citer.nums, which appends on first sight.
    # Calling nums() again is safe because keys already exist: nums() will not append duplicates.
    def sub(match):
        keys = [k.strip() for k in match.group(1).split("|")]
        return "[" + Citer.render(citer.nums(keys)) + "]"
    return re.sub(r"\[\[([^\]]+)\]\]", sub, rendered)


if __name__ == "__main__":
    build()
