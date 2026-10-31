#!/usr/bin/env python3
"""
Generate Figures 4, 5, 6, and 7 for the SCI manuscript:
Surgical Treatment of Hepatic Alveolar Echinococcosis (2000 - Oct 31, 2026).
Follows nature-figure contract:
- Editable TrueType text in PDF (pdf.fonttype = 42) and SVG (svg.fonttype = 'none')
- Minimum rendered glyph size >= 5 pt
- Multi-panel alignment verified via require_matplotlib_panel_alignment() (<= 1.5 pt)
- Zero text-text or text-stroke collisions verified via audit_figure_collisions.py
"""

import csv
import math
import os
import re
import sys
from collections import Counter, defaultdict
from itertools import combinations

import matplotlib as mpl
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, "/workspace/skills/nature-figure/scripts")
sys.path.insert(0, "/workspace/bibliometrics_hae")

from audit_panel_alignment import require_matplotlib_panel_alignment
from clean_wos_hae import parse_fields, parse_wos_records
from generate_figures_part1 import (
    OUT_FIG_DIR,
    OUT_SRC_DIR,
    PAL,
    STRICT_PATH,
    add_panel_label,
    draw_radial_network,
)
from generate_summary_tables import calc_h_index

mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica", "sans-serif"],
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "font.size": 6.5,
    "axes.titlesize": 7.5,
    "axes.labelsize": 6.8,
    "xtick.labelsize": 6.0,
    "ytick.labelsize": 6.0,
    "legend.fontsize": 6.0,
    "axes.spines.right": False,
    "axes.spines.top": False,
    "axes.linewidth": 0.75,
    "xtick.major.width": 0.7,
    "ytick.major.width": 0.7,
    "legend.frameon": False,
})


# Generic disease-name terms (e.g. "alveolar echinococcosis") occur in most records and are
# deliberately excluded from every theme so that theme counts reflect clinical content.
THEMES = {
    "ELRA & vascular reconstruction": {
        "terms": {
            "ex vivo liver resection and autotransplantation", "inferior vena cava",
            "vascular reconstruction", "budd-chiari syndrome", "venovenous bypass",
            "retrohepatic inferior vena cava resection", "inferior vena cava replacement",
        },
        "tick": "ELRA/\nvascular", "short": "ELRA & vascular", "color": PAL["coral"],
        "label_offset": (-7, 0, "right"),
    },
    "Hepatectomy & postoperative outcomes": {
        "terms": {
            "hepatectomy", "surgical treatment", "radical resection", "postoperative complications",
            "biliary complications", "palliative surgery", "outcomes", "radical hepatic resection",
            "palliative hepatic resection", "survival", "prognosis",
        },
        "tick": "Hepat-\nectomy", "short": "Hepatectomy", "color": PAL["amber"],
        "label_offset": (0, 9, "center"),
    },
    "Liver transplantation & recurrence": {
        "terms": {
            "liver transplantation", "transplantation", "living donor liver transplantation",
            "recurrence", "follow-up", "immunosuppression", "graft", "donor liver",
        },
        "tick": "LTx/\nrecurr.", "short": "LTx & recurrence", "color": PAL["teal"],
        "label_offset": (0, -11, "center"),
    },
    "Staging & imaging": {
        "terms": {
            "diagnosis", "classification", "computed tomography", "pet/ct", "ultrasonography",
            "magnetic resonance imaging", "mri findings", "contrast-enhanced ultrasound", "fdg-pet",
            "18f-fdg pet", "f-18-fdg pet/ct", "pet",
        },
        "tick": "Staging/\nimaging", "short": "Staging & imaging", "color": PAL["blue"],
        "label_offset": (0, 9, "center"),
    },
    "Antiparasitic therapy": {
        "terms": {"albendazole", "antiparasitic therapy", "benzimidazoles", "mebendazole"},
        "tick": "Anti-\nparasitic", "short": "Albendazole", "color": PAL["plum"],
        "label_offset": (0, 9, "center"),
    },
    "Minimally invasive & interventional": {
        "terms": {
            "laparoscopic hepatectomy", "laparoscopic treatment", "laparoscopic approach",
            "laparoscopic pericystectomy", "robotic liver surgery", "robotic surgery",
            "robotic liver resection", "minimally invasive surgery", "minimally invasive",
            "minimally invasive liver surgery", "percutaneous treatment", "percutaneous drainage",
            "microwave ablation", "radiofrequency ablation", "radiofrequency thermal ablation",
            "endoscopic retrograde cholangiopancreatography",
            "endoscopic retrograde cholangio-pancreatography (ercp)", "endoscopic management",
            "biliary drainage", "biliary stent",
        },
        "tick": "Minimally\ninvasive", "short": "Minimally invasive", "color": PAL["sage"],
        "label_offset": (0, 9, "center"),
    },
}


def record_keywords(d):
    kws = set()
    for tag in ("DE", "ID"):
        if d.get(tag):
            kws.update(x.strip().lower() for x in " ".join(d[tag]).split(";") if x.strip())
    return kws


def compute_callon_metrics(kw_counts, kw_edges, min_freq=3):
    """Callon centrality (10 x sum of external equivalence indices) and density
    (100 x sum of internal equivalence indices / number of theme terms), with
    equivalence index e_ij = c_ij^2 / (c_i * c_j) over keywords occurring >= min_freq times."""
    vocab = {k for k, v in kw_counts.items() if v >= min_freq}
    metrics = {}
    for t_name, t in THEMES.items():
        members = t["terms"] & vocab
        ext, internal = 0.0, 0.0
        for (k1, k2), c in kw_edges.items():
            if k1 not in vocab or k2 not in vocab:
                continue
            e = c * c / (kw_counts[k1] * kw_counts[k2])
            in1, in2 = k1 in members, k2 in members
            if in1 and in2:
                internal += e
            elif in1 or in2:
                ext += e
        metrics[t_name] = (10.0 * ext, 100.0 * internal / max(len(members), 1))
    return metrics


def export_figure(fig, basename, single_panel=False, row_groups=None, column_groups=None, exclude_axes=()):
    base_path = os.path.join(OUT_FIG_DIR, basename)
    if not single_panel:
        require_matplotlib_panel_alignment(
            fig,
            json_out=f"{base_path}.alignment.json",
            overlay_svg=f"{base_path}.alignment.svg",
            tolerance_pt=1.5,
            gutter_tolerance_pt=1.5,
            require_panel_labels=True,
            row_groups=row_groups,
            column_groups=column_groups,
            exclude_axes=exclude_axes,
            strict=True,
        )
    fig.savefig(f"{base_path}.pdf", bbox_inches="tight", pad_inches=0.08)
    fig.savefig(f"{base_path}.svg", bbox_inches="tight", pad_inches=0.08)
    fig.savefig(f"{base_path}.png", dpi=600, bbox_inches="tight", pad_inches=0.08)
    fig.savefig(f"{base_path}.tiff", dpi=600, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)
    print(f"Exported {basename} (.pdf, .svg, .png, .tiff)")


# ===========================================================================
# FIGURE 4: Prolific Authors, Temporal Trajectories, Core Journals & Bradford's Law
# ===========================================================================
def build_fig4_authors_journals(records):
    author_pubs = Counter()
    author_cites = defaultdict(list)
    author_year_pubs = defaultdict(Counter)
    author_year_cites = defaultdict(Counter)
    author_edges = Counter()

    journal_pubs = Counter()
    journal_cites = defaultdict(list)

    for d in records:
        py = int(d["PY"][0].strip())
        tc = int(d["TC"][0].strip()) if d.get("TC") and d["TC"][0].strip().isdigit() else 0
        so = " ".join(d.get("SO", [])).strip()

        afs = sorted({x.strip() for x in d.get("AF", []) if x.strip() and x.strip() != "[Anonymous]"})
        for a in afs:
            author_pubs[a] += 1
            author_cites[a].append(tc)
            author_year_pubs[a][py] += 1
            author_year_cites[a][py] += tc
        for a1, a2 in combinations(afs, 2):
            author_edges[(a1, a2)] += 1

        if so:
            journal_pubs[so] += 1
            journal_cites[so].append(tc)

    # Save source data CSV
    with open(os.path.join(OUT_SRC_DIR, "fig4_authors_journals.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Category", "Name", "Publications", "Total_Citations", "CPP", "H_Index"])
        for a, cnt in author_pubs.most_common(15):
            tc_s = sum(author_cites[a])
            w.writerow(["Author", a, cnt, tc_s, round(tc_s / cnt, 2), calc_h_index(author_cites[a])])
        for so, cnt in journal_pubs.most_common(15):
            tc_s = sum(journal_cites[so])
            w.writerow(["Journal", so, cnt, tc_s, round(tc_s / cnt, 2), calc_h_index(journal_cites[so])])

    fig = plt.figure(figsize=(7.2, 6.0))
    gs = fig.add_gridspec(2, 2, left=0.19, right=0.96, bottom=0.08, top=0.93, wspace=0.42, hspace=0.38)
    ax_a = fig.add_subplot(gs[0, 0])
    ax_b = fig.add_subplot(gs[0, 1])
    ax_c = fig.add_subplot(gs[1, 0])
    ax_d = fig.add_subplot(gs[1, 1])

    # --- Panel a: Author Co-authorship Network (Top 12 Authors) ---
    top12_au = [x[0] for x in author_pubs.most_common(12)]
    short_au = {
        "Aji, Tuerganaili": "Aji T",
        "Wen, Hao": "Wen H",
        "Shao, Yingmei": "Shao YM",
        "Vuitton, Dominique Angele": "Vuitton DA",
        "Wang, Wentao": "Wang WT",
        "Jiang, Tiemin": "Jiang TM",
        "Bresson-Hadni, Solange": "Bresson-Hadni S",
        "Fan, Haining": "Fan HN",
        "Yang, Xianwei": "Yang XW",
        "Gottstein, Bruno": "Gottstein B",
        "Gruener, Beate": "Gruener B",
        "Kern, Peter": "Kern P",
    }
    au_colors = {}
    for a in top12_au:
        if a in {"Aji, Tuerganaili", "Wen, Hao", "Shao, Yingmei", "Jiang, Tiemin"}:
            au_colors[a] = PAL["coral"]  # Xinjiang ELRA cluster
        elif a in {"Wang, Wentao", "Yang, Xianwei", "Fan, Haining"}:
            au_colors[a] = PAL["amber"]  # West China & Qinghai cluster
        else:
            au_colors[a] = PAL["teal"]   # European consortium cluster

    draw_radial_network(ax_a, top12_au, author_pubs, author_edges, au_colors, short_labels=short_au)
    ax_a.set_title("Core author collaboration network", pad=6)

    # --- Panel b: Top 10 Authors' Production Over Time (2000-2026) ---
    top10_au = [x[0] for x in author_pubs.most_common(10)][::-1]
    y_idx = np.arange(len(top10_au))
    for i, a in enumerate(top10_au):
        ys = sorted(author_year_pubs[a].keys())
        if ys:
            ax_b.plot([min(ys), max(ys)], [i, i], color="#D0D7DE", linewidth=0.8, zorder=1)
        for y in ys:
            cnt = author_year_pubs[a][y]
            c_yr = author_year_cites[a][y]
            col = PAL["coral"] if c_yr >= 50 else (PAL["blue"] if c_yr >= 15 else PAL["sky"])
            ax_b.scatter([y], [i], s=14 + 13 * cnt, color=col, edgecolors="none", alpha=0.9, zorder=3)

    ax_b.set_yticks(y_idx)
    ax_b.set_yticklabels([short_au.get(a, a) for a in top10_au])
    ax_b.set_xlim(1999, 2027.5)
    ax_b.set_ylim(-0.7, len(top10_au) - 0.3)
    ax_b.set_xticks([2000, 2005, 2010, 2015, 2020, 2026])
    ax_b.set_xlabel("Publication year")
    ax_b.set_title("Top authors' output over time", pad=6)

    # --- Panel c: Top 10 Core Journals ---
    short_so = {
        "WORLD JOURNAL OF GASTROENTEROLOGY": "World J Gastroenterol",
        "MEDICINE": "Medicine",
        "BMC INFECTIOUS DISEASES": "BMC Infect Dis",
        "PATHOGENS": "Pathogens",
        "PLOS NEGLECTED TROPICAL DISEASES": "PLoS Negl Trop Dis",
        "LANGENBECKS ARCHIVES OF SURGERY": "Langenbecks Arch Surg",
        "ACTA TROPICA": "Acta Trop",
        "HELMINTHOLOGIA": "Helminthologia",
        "FRONTIERS IN SURGERY": "Front Surg",
        "AMERICAN JOURNAL OF TROPICAL MEDICINE AND HYGIENE": "Am J Trop Med Hyg",
    }
    top10_so = journal_pubs.most_common(10)[::-1]
    so_labels = [short_so.get(x[0], x[0].title()) for x in top10_so]
    so_vals = [x[1] for x in top10_so]
    so_cpps = [round(sum(journal_cites[x[0]]) / x[1], 1) for x in top10_so]
    y_so = np.arange(len(so_labels))

    so_cols = [PAL["coral"] if cpp >= 30 else PAL["blue"] for cpp in so_cpps]
    ax_c.barh(y_so, so_vals, height=0.62, color=so_cols, edgecolor="none")
    ax_c.set_yticks(y_so)
    ax_c.set_yticklabels(so_labels)
    ax_c.set_xlim(0, 22.5)
    ax_c.set_xlabel("Publications (n)")
    ax_c.set_title("Top 10 core journals", pad=6)
    for y, v, cpp_v in zip(y_so, so_vals, so_cpps):
        ax_c.text(v + 0.35, y, f"{v} (CPP: {cpp_v})", va="center", ha="left", fontsize=5.4, color="#222222")

    # --- Panel d: Bradford's Law of Scattering Across Journals ---
    all_so_sorted = journal_pubs.most_common()
    ranks = np.clip(np.arange(1, len(all_so_sorted) + 1, dtype=float), 1.0, None)
    cum_so_pubs = np.cumsum([x[1] for x in all_so_sorted])
    total_p = cum_so_pubs[-1]
    z1_end = int(np.searchsorted(cum_so_pubs, total_p / 3.0) + 1)
    z2_end = int(np.searchsorted(cum_so_pubs, 2.0 * total_p / 3.0) + 1)

    ax_d.axvspan(1, z1_end, color="#FDF3EE", alpha=0.75, lw=0, zorder=0)
    ax_d.axvspan(z1_end, z2_end, color="#EBF3FA", alpha=0.65, lw=0, zorder=0)
    ax_d.axvspan(z2_end, len(ranks), color="#F2F4F7", alpha=0.75, lw=0, zorder=0)

    ax_d.plot(ranks, cum_so_pubs, color=PAL["navy"], linewidth=1.5, zorder=3)
    ax_d.scatter([z1_end, z2_end], [cum_so_pubs[z1_end - 1], cum_so_pubs[z2_end - 1]], color=PAL["coral"], s=20, zorder=4)
    ax_d.set_xscale("log")
    ax_d.set_xlim(0.9, len(ranks) * 1.15)
    ax_d.set_ylim(0, 420)
    ax_d.xaxis.set_major_formatter(mpl.ticker.ScalarFormatter())
    ax_d.xaxis.set_minor_formatter(mpl.ticker.NullFormatter())
    ax_d.tick_params(axis="x", which="minor", bottom=False)
    bradford_ticks = [1, 5, z1_end, z2_end, len(ranks)]
    ax_d.set_xticks(bradford_ticks)
    ax_d.set_xticklabels([str(t) for t in bradford_ticks])
    ax_d.set_xlabel("Journal rank (log scale)")
    ax_d.set_ylabel("Cumulative publications (n)")
    ax_d.set_title("Bradford's law journal zones", pad=6)

    ax_d.text(3.2, 330, f"Core Zone 1\n({z1_end} j.)", ha="center", va="top", fontsize=5.3, color=PAL["coral"], fontweight="bold")
    ax_d.text(32.5, 125, f"Zone 2\n({z2_end - z1_end} j.)", ha="center", va="top", fontsize=5.3, color=PAL["navy"])
    ax_d.text(105.0, 95, f"Zone 3\n({len(ranks) - z2_end} j.)", ha="center", va="top", fontsize=5.3, color=PAL["slate"])

    add_panel_label(fig, ax_a, "a", dx_pt=-48, dy_pt=6)
    add_panel_label(fig, ax_b, "b", dx_pt=-38, dy_pt=6)
    add_panel_label(fig, ax_c, "c", dx_pt=-48, dy_pt=6)
    add_panel_label(fig, ax_d, "d", dx_pt=-38, dy_pt=6)

    export_figure(
        fig, "fig4_authors_journals",
        row_groups=[["a", "b"], ["c", "d"]],
        column_groups=[["a", "c"], ["b", "d"]]
    )


# ===========================================================================
# FIGURE 5: Co-Cited References Network & Landmark Knowledge Base (Panels a, b)
# ===========================================================================
def build_fig5_cocitation_analysis(records):
    cr_counts = Counter()
    cr_cooccur = Counter()

    for d in records:
        crs = sorted({x.strip() for x in d.get("CR", []) if x.strip()})
        for c in crs:
            cr_counts[c] += 1
        for c1, c2 in combinations(crs, 2):
            cr_cooccur[(c1, c2)] += 1

    top15_cr = cr_counts.most_common(15)

    def format_cr_short(cr_str):
        parts = [x.strip() for x in cr_str.split(",")]
        au = parts[0].title() if parts else cr_str
        au = re.sub(r"\s+([A-Za-z]+)$", lambda m: " " + m.group(1).upper(), au)
        yr = parts[1] if len(parts) > 1 else ""
        j = parts[2].title() if len(parts) > 2 else ""
        j_map = {
            "Acta Trop": "Acta Trop",
            "Parasitol Int": "Parasitol Int",
            "Clin Microbiol Rev": "Clin Microbiol Rev",
            "Eur J Gastroen Hepat": "Eur J Gastroen",
            "Transplantation": "Transplantation",
            "Lancet": "Lancet",
            "Emerg Infect Dis": "Emerg Infect Dis",
            "Adv Parasit": "Adv Parasitol",
            "B World Health Organ": "Bull WHO",
            "J Hepatol": "J Hepatol",
            "Gastroenterol Clin N": "Gastroenterol Clin",
            "Curr Opin Infect Dis": "Curr Opin Infect",
            "Langenbeck Arch Surg": "Langenbecks Arch",
            "Plos Neglect Trop D": "PLoS Negl Trop",
        }
        j_short = j_map.get(j, j[:14])
        return f"{au} ({yr}, {j_short})"

    with open(os.path.join(OUT_SRC_DIR, "fig5_cocitation_landmarks.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Rank", "Short_Label", "Raw_WoS_Reference", "Co_Citations"])
        for idx, (cr_raw, cnt) in enumerate(top15_cr, 1):
            w.writerow([idx, format_cr_short(cr_raw), cr_raw, cnt])

    fig = plt.figure(figsize=(7.2, 3.35))
    gs = fig.add_gridspec(1, 2, left=0.06, right=0.96, bottom=0.14, top=0.88, wspace=0.68)
    ax_a = fig.add_subplot(gs[0, 0])
    ax_b = fig.add_subplot(gs[0, 1])

    # --- Panel a: Co-citation Network of Top 12 Landmark References ---
    top12_cr_keys = [x[0] for x in top15_cr[:12]]
    cr_short_net = {}
    cr_net_colors = {}
    for k in top12_cr_keys:
        parts = [x.strip() for x in k.split(",")]
        au_yr = f"{parts[0].split()[0].title()} {parts[1]}"
        if au_yr in cr_short_net.values():
            au_yr = f"{parts[0].split()[0].title()} {parts[1]}b"
        cr_short_net[k] = au_yr
        # Assign knowledge cluster color:
        # Coral: Surgical & Transplant cohorts (Bresson-Hadni 2000, Koch 2003, Wen 2019)
        # Teal: WHO Staging & Consensus (Brunetti 2010, Kern 2006, Vuitton 1996, Kern 2017)
        # Blue: Epidemiology, Natural History & Medical Therapy (McManus 2003, Kern 2003, Deplazes 2017, Torgerson 2008, Ammann 1996)
        if any(s in k for s in ["Bresson-Hadni S, 2000", "Koch SP, 2003", "Wen H, 2019"]):
            cr_net_colors[k] = PAL["coral"]
        elif any(s in k for s in ["Brunetti E, 2010", "Kern P, 2006", "Vuitton DA, 1996", "Kern P, 2017"]):
            cr_net_colors[k] = PAL["teal"]
        else:
            cr_net_colors[k] = PAL["blue"]

    draw_radial_network(ax_a, top12_cr_keys, cr_counts, cr_cooccur, cr_net_colors, short_labels=cr_short_net, size_scale=0.35)
    ax_a.set_title("Co-cited reference network", pad=6)

    # --- Panel b: Top 12 Most Co-Cited References Horizontal Bar Chart ---
    top12_rev = top15_cr[:12][::-1]
    labels_b = [format_cr_short(x[0]) for x in top12_rev]
    vals_b = [x[1] for x in top12_rev]
    cols_b = [cr_net_colors[x[0]] for x in top12_rev]
    y_b = np.arange(len(labels_b))

    ax_b.barh(y_b, vals_b, height=0.64, color=cols_b, edgecolor="none")
    ax_b.set_yticks(y_b)
    ax_b.set_yticklabels(labels_b, fontsize=5.5)
    ax_b.set_xlim(0, 185)
    ax_b.set_xlabel("Co-citation frequency (n)")
    ax_b.set_title("Top 12 co-cited milestone references", pad=6)
    for y, v in zip(y_b, vals_b):
        ax_b.text(v + 2.5, y, str(v), va="center", ha="left", fontsize=5.5, color="#222222")

    add_panel_label(fig, ax_a, "a", dx_pt=-16, dy_pt=6)
    add_panel_label(fig, ax_b, "b", dx_pt=-46, dy_pt=6)

    export_figure(
        fig, "fig5_cocitation_analysis",
        row_groups=[["a", "b"]]
    )


# ===========================================================================
# FIGURE 6: Keyword Co-Occurrence, APY Evolution, Cluster Trends & Strategic Map
# ===========================================================================
def build_fig6_keyword_cooccurrence(records):
    kw_counts = Counter()
    kw_years = defaultdict(list)
    kw_edges = Counter()
    theme_phase_counts = {t: [0, 0, 0] for t in THEMES}

    for d in records:
        py = int(d["PY"][0].strip())
        phase_idx = 0 if py <= 2009 else (1 if py <= 2018 else 2)
        kws = record_keywords(d)

        for k in kws:
            kw_counts[k] += 1
            kw_years[k].append(py)
        for k1, k2 in combinations(sorted(kws), 2):
            kw_edges[(k1, k2)] += 1

        for t_name, t in THEMES.items():
            if kws & t["terms"]:
                theme_phase_counts[t_name][phase_idx] += 1

    callon = compute_callon_metrics(kw_counts, kw_edges)

    with open(os.path.join(OUT_SRC_DIR, "fig6_keywords_clusters.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Keyword", "Frequency", "Mean_Publication_Year"])
        for k, cnt in kw_counts.most_common(30):
            apy = round(sum(kw_years[k]) / len(kw_years[k]), 2)
            w.writerow([k, cnt, apy])

    with open(os.path.join(OUT_SRC_DIR, "fig6_theme_callon_metrics.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Theme", "Terms", "Records_with_theme", "Callon_Centrality", "Callon_Density",
                    "Records_2000_2009", "Records_2010_2018", "Records_2019_2026"])
        for t_name, t in THEMES.items():
            c, dens = callon[t_name]
            w.writerow([t_name, "; ".join(sorted(t["terms"])), sum(theme_phase_counts[t_name]),
                        round(c, 3), round(dens, 3)]
                       + theme_phase_counts[t_name])

    fig = plt.figure(figsize=(7.2, 6.0))
    gs = fig.add_gridspec(2, 2, left=0.20, right=0.96, bottom=0.08, top=0.93, wspace=0.42, hspace=0.38)
    ax_a = fig.add_subplot(gs[0, 0])
    ax_b = fig.add_subplot(gs[0, 1])
    ax_c = fig.add_subplot(gs[1, 0])
    ax_d = fig.add_subplot(gs[1, 1])

    # --- Panel a: Co-occurrence Network of 12 Core Clinical Keywords ---
    net_kws = [
        "alveolar echinococcosis",
        "hepatic alveolar echinococcosis",
        "hepatectomy",
        "ex vivo liver resection and autotransplantation",
        "liver transplantation",
        "surgical treatment",
        "diagnosis",
        "follow-up",
        "albendazole",
        "classification",
        "inferior vena cava",
        "vascular reconstruction",
    ]
    short_kw = {
        "alveolar echinococcosis": "Alveolar AE",
        "hepatic alveolar echinococcosis": "Hepatic AE",
        "hepatectomy": "Hepatectomy",
        "ex vivo liver resection and autotransplantation": "ELRA",
        "liver transplantation": "Liver transpl",
        "surgical treatment": "Surgery",
        "diagnosis": "Diagnosis",
        "follow-up": "Follow-up",
        "albendazole": "Albendazole",
        "classification": "Classification",
        "inferior vena cava": "IVC",
        "vascular reconstruction": "Vasc reconstr",
    }
    kw_cols = {}
    for k in net_kws:
        kw_cols[k] = PAL["grey"]
        for t in THEMES.values():
            if k in t["terms"]:
                kw_cols[k] = t["color"]
                break

    draw_radial_network(ax_a, net_kws, kw_counts, kw_edges, kw_cols, short_labels=short_kw, size_scale=0.45)
    ax_a.set_title("Core keyword co-occurrence network", pad=6)

    # --- Panel b: Clinical & Surgical Keywords Ranked by Average Publication Year (APY) ---
    evo_kws = [
        "vascular reconstruction",
        "ex vivo liver resection and autotransplantation",
        "hepatectomy",
        "classification",
        "inferior vena cava",
        "postoperative complications",
        "hepatic alveolar echinococcosis",
        "diagnosis",
        "surgical treatment",
        "liver transplantation",
        "computed tomography",
        "follow-up",
        "pet/ct",
        "recurrence",
        "albendazole",
        "antiparasitic therapy",
    ][::-1]
    evo_apys = [sum(kw_years[k]) / len(kw_years[k]) for k in evo_kws]
    evo_cnts = [kw_counts[k] for k in evo_kws]
    evo_labels = [
        "Vascular reconstr" if k == "vascular reconstruction"
        else ("ELRA" if k == "ex vivo liver resection and autotransplantation"
              else ("Hepatic AE" if k == "hepatic alveolar echinococcosis"
                    else ("Postop complications" if k == "postoperative complications"
                          else ("Antiparasitic therapy" if k == "antiparasitic therapy"
                                else ("PET/CT" if k == "pet/ct" else k.capitalize())))))
        for k in evo_kws
    ]
    y_evo = np.arange(len(evo_kws))
    for y, apy_v, cnt_v in zip(y_evo, evo_apys, evo_cnts):
        col = PAL["coral"] if apy_v >= 2019.5 else (PAL["blue"] if apy_v >= 2016.0 else PAL["teal"])
        ax_b.plot([2010.0, apy_v], [y, y], color="#D8DEE4", linewidth=0.8, zorder=1)
        ax_b.scatter([apy_v], [y], s=18 + 0.9 * cnt_v, color=col, edgecolors="none", zorder=3)

    ax_b.set_yticks(y_evo)
    ax_b.set_yticklabels(evo_labels, fontsize=5.3)
    ax_b.set_xlim(2010.0, 2023.2)
    ax_b.set_xticks([2011, 2014, 2017, 2020, 2022])
    ax_b.set_xlabel("Average publication year (APY)")
    ax_b.set_title("Temporal shift of surgical & clinical terms", pad=6)

    # --- Panel c: Theme trajectories across the three phases ---
    t_names = list(THEMES.keys())
    x_c = np.arange(len(t_names))
    w_bar = 0.26
    p1_vals = [theme_phase_counts[k][0] for k in t_names]
    p2_vals = [theme_phase_counts[k][1] for k in t_names]
    p3_vals = [theme_phase_counts[k][2] for k in t_names]

    ax_c.bar(x_c - w_bar, p1_vals, width=w_bar, color=PAL["sky"], label="2000–2009")
    ax_c.bar(x_c, p2_vals, width=w_bar, color=PAL["blue"], label="2010–2018")
    ax_c.bar(x_c + w_bar, p3_vals, width=w_bar, color=PAL["coral"], label="2019–2026")
    ax_c.set_xticks(x_c)
    ax_c.set_xticklabels([THEMES[k]["tick"] for k in t_names], fontsize=5.2)
    ax_c.set_ylim(0, max(max(p1_vals), max(p2_vals), max(p3_vals)) * 1.32)
    ax_c.set_ylabel("Publications mentioning theme (n)")
    ax_c.legend(loc="upper left", fontsize=5.5)
    ax_c.set_title("Theme trajectory across three phases", pad=6)

    # --- Panel d: Strategic diagram from computed Callon centrality and density ---
    cents = np.array([callon[k][0] for k in t_names])
    dens = np.array([callon[k][1] for k in t_names])
    med_c, med_d = float(np.median(cents)), float(np.median(dens))
    ax_d.axhline(med_d, color="#D0D7DE", linestyle="-", linewidth=0.7, zorder=1)
    ax_d.axvline(med_c, color="#D0D7DE", linestyle="-", linewidth=0.7, zorder=1)

    x_pad = (cents.max() - cents.min()) * 0.30
    y_pad = (dens.max() - dens.min()) * 0.30
    x_lo, x_hi = cents.min() - x_pad, cents.max() + x_pad
    y_hi = dens.max() + y_pad
    y_lo = -0.16 * y_hi
    for k, cx, cy in zip(t_names, cents, dens):
        n_rec = sum(theme_phase_counts[k])
        ax_d.scatter([cx], [cy], s=20 + 0.9 * n_rec, color=THEMES[k]["color"], alpha=0.88, edgecolors="none", zorder=3)
        dx, dy, ha = THEMES[k]["label_offset"]
        ax_d.annotate(THEMES[k]["short"], xy=(cx, cy), xytext=(dx, dy), textcoords="offset points",
                      ha=ha, va="center", fontsize=5.3, fontweight="bold", color="#222222", zorder=4)

    ax_d.text(0.97, 0.97, "Motor", transform=ax_d.transAxes, ha="right", va="top", fontsize=5.3, color=PAL["coral"], fontweight="bold")
    ax_d.text(0.03, 0.97, "Niche", transform=ax_d.transAxes, ha="left", va="top", fontsize=5.3, color=PAL["plum"], fontweight="bold")
    ax_d.text(0.97, 0.03, "Basic", transform=ax_d.transAxes, ha="right", va="bottom", fontsize=5.3, color=PAL["blue"], fontweight="bold")
    ax_d.text(0.03, 0.03, "Emerging/declining", transform=ax_d.transAxes, ha="left", va="bottom", fontsize=5.3, color=PAL["amber"], fontweight="bold")

    ax_d.set_xlim(x_lo, x_hi)
    ax_d.set_ylim(y_lo, y_hi)
    ax_d.set_yticks([t for t in ax_d.get_yticks() if 0 <= t <= y_hi])
    ax_d.set_xlabel("Callon centrality (external links)")
    ax_d.set_ylabel("Callon density (internal links)")
    ax_d.set_title("Thematic strategic diagram", pad=6)

    add_panel_label(fig, ax_a, "a", dx_pt=-45, dy_pt=6)
    add_panel_label(fig, ax_b, "b", dx_pt=-45, dy_pt=6)
    add_panel_label(fig, ax_c, "c", dx_pt=-45, dy_pt=6)
    add_panel_label(fig, ax_d, "d", dx_pt=-45, dy_pt=6)

    export_figure(
        fig, "fig6_keyword_cooccurrence",
        row_groups=[["a", "b"], ["c", "d"]],
        column_groups=[["a", "c"], ["b", "d"]]
    )


# ===========================================================================
# FIGURE 7: Curated Keyword Bursts (2000-2026) & Surgical Modality Heatmap
# ===========================================================================
def build_fig7_keyword_bursts(records):
    years = list(range(2000, 2027))
    year_totals = Counter()
    kw_year = defaultdict(Counter)

    for d in records:
        py = int(d["PY"][0].strip())
        year_totals[py] += 1
        kws = set()
        if d.get("DE"):
            kws.update(x.strip().lower() for x in " ".join(d["DE"]).split(";") if x.strip())
        if d.get("ID"):
            kws.update(x.strip().lower() for x in " ".join(d["ID"]).split(";") if x.strip())
        for k in kws:
            kw_year[k][py] += 1

    N_all = sum(year_totals.values())

    def llr_burst(k_in, n_in, k_total, n_total):
        if k_in == 0 or n_in == 0 or n_in == n_total:
            return 0.0
        p1 = k_in / n_in
        p0 = k_total / n_total
        if p1 <= p0:
            return 0.0
        k_out = k_total - k_in
        n_out = n_total - n_in
        p2 = k_out / n_out if n_out > 0 else 0.0

        def term(k, n, p):
            if k == 0 or p <= 0 or k == n or p >= 1:
                return 0.0
            return k * math.log(p) + (n - k) * math.log(1 - p)

        return max(0.0, (term(k_in, n_in, p1) + term(k_out, n_out, p2) - term(k_total, n_total, p0)))

    curated_candidates = [
        "antiparasitic therapy",
        "antigen",
        "albendazole",
        "hydatid disease",
        "echinococcus multilocularis",
        "follow-up",
        "pet/ct",
        "experience",
        "management",
        "clinical features",
        "postoperative complications",
        "living donor liver transplantation",
        "classification",
        "hepatectomy",
        "inferior vena cava",
        "hepatic alveolar echinococcosis",
        "outcomes",
        "transplantation",
        "ex vivo liver resection and autotransplantation",
        "vascular reconstruction",
    ]

    burst_rows = []
    for kw in curated_candidates:
        y_cnts = kw_year[kw]
        k_tot = sum(y_cnts.values())
        best_s = 0.0
        best_span = (2000, 2005)
        for i1 in range(len(years)):
            for i2 in range(i1 + 1, len(years)):
                y1, y2 = years[i1], years[i2]
                span = y2 - y1 + 1
                if span < 2 or span > 12:
                    continue
                if y_cnts[y1] == 0 or y_cnts[y2] == 0:
                    continue
                k_in = sum(y_cnts[y] for y in range(y1, y2 + 1))
                n_in = sum(year_totals[y] for y in range(y1, y2 + 1))
                s = llr_burst(k_in, n_in, k_tot, N_all)
                if s > best_s:
                    best_s = s
                    best_span = (y1, y2)
        burst_rows.append((kw, round(best_s, 2), best_span[0], best_span[1], k_tot))

    # Sort chronologically by burst start year, then by strength
    burst_rows.sort(key=lambda x: (x[2], x[3], -x[1]))

    with open(os.path.join(OUT_SRC_DIR, "fig7_keyword_bursts.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Keyword", "Burst_Strength", "Begin_Year", "End_Year", "Total_Frequency"])
        for r in burst_rows:
            w.writerow(list(r))

    fig = plt.figure(figsize=(7.2, 4.4))
    gs = fig.add_gridspec(1, 2, left=0.22, right=0.96, bottom=0.13, top=0.89, wspace=0.48)
    ax_a = fig.add_subplot(gs[0, 0])
    ax_b = fig.add_subplot(gs[0, 1])

    # --- Panel a: LLR keyword bursts for 20 curated clinical terms ---
    rev_rows = burst_rows[::-1]
    short_burst_lbl = {
        "ex vivo liver resection and autotransplantation": "ELRA (autotransplantation)",
        "living donor liver transplantation": "Living-donor LTx",
        "hepatic alveolar echinococcosis": "Hepatic AE",
        "echinococcus multilocularis": "E. multilocularis",
        "postoperative complications": "Postop complications",
        "vascular reconstruction": "Vascular reconstruction",
        "antiparasitic therapy": "Antiparasitic therapy",
        "inferior vena cava": "Inferior vena cava",
        "clinical features": "Clinical features",
        "hydatid disease": "Hydatid disease",
        "pet/ct": "18F-FDG PET/CT",
    }
    y_b = np.arange(len(rev_rows))
    for i, (kw, s, y1, y2, ktot) in enumerate(rev_rows):
        # Baseline bar 2000-2026
        ax_a.plot([2000, 2026], [i, i], color="#D6E4F0", linewidth=3.8, solid_capstyle="butt", zorder=1)
        # Burst segment y1-y2
        ax_a.plot([y1, y2], [i, i], color=PAL["crimson"], linewidth=3.8, solid_capstyle="butt", zorder=2)
        ax_a.text(2026.6, i, f"{s:.1f} ({y1}–{str(y2)[2:]})", va="center", ha="left", fontsize=5.1, color="#222222")

    ax_a.set_yticks(y_b)
    ax_a.set_yticklabels([short_burst_lbl.get(r[0], r[0].capitalize()) for r in rev_rows], fontsize=5.3)
    ax_a.set_xlim(1999.5, 2036.5)
    ax_a.set_xticks([2000, 2005, 2010, 2015, 2020, 2026])
    ax_a.set_xlabel("Timeline (2000–2026) & burst strength")
    ax_a.set_title("Keyword bursts (20 curated clinical terms)", pad=6)

    # --- Panel b: Surgical & Clinical Modality Shift Across 5 Periods ---
    periods = ["2000–05", "2006–10", "2011–15", "2016–20", "2021–26"]
    period_ranges = [(2000, 2005), (2006, 2010), (2011, 2015), (2016, 2020), (2021, 2026)]
    mi_terms = THEMES["Minimally invasive & interventional"]["terms"]
    modalities = [
        ("ELRA", {"ex vivo liver resection and autotransplantation"}),
        ("Vascular / IVC", {"vascular reconstruction", "inferior vena cava"}),
        ("Hepatectomy", {"hepatectomy", "radical resection"}),
        ("Liver transplantation", {"liver transplantation", "living donor liver transplantation", "transplantation"}),
        ("Laparoscopic / robotic", {k for k in mi_terms if "laparoscop" in k or "robotic" in k or "minimally" in k}),
        ("Percutaneous / ERCP", {k for k in mi_terms if not ("laparoscop" in k or "robotic" in k or "minimally" in k)}),
        ("Staging, CT/MRI/US", {"classification", "computed tomography", "magnetic resonance imaging", "ultrasonography"}),
        ("18F-FDG PET/CT", {"pet/ct", "fdg-pet", "18f-fdg pet", "f-18-fdg pet/ct", "pet"}),
        ("Albendazole", {"albendazole", "antiparasitic therapy", "benzimidazoles"}),
    ]

    mat = np.zeros((len(modalities), len(periods)), dtype=int)
    for d in records:
        py = int(d["PY"][0].strip())
        kws = record_keywords(d)
        for p_idx, (y_start, y_end) in enumerate(period_ranges):
            if y_start <= py <= y_end:
                for m_idx, (_, m_set) in enumerate(modalities):
                    if kws & m_set:
                        mat[m_idx, p_idx] += 1

    with open(os.path.join(OUT_SRC_DIR, "fig7b_modality_heatmap.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Modality", "Terms"] + periods)
        for (m_name, m_set), row in zip(modalities, mat):
            w.writerow([m_name, "; ".join(sorted(m_set))] + [int(v) for v in row])

    im = ax_b.imshow(mat, cmap="YlGnBu", aspect="auto")
    ax_b.set_xticks(np.arange(len(periods)))
    ax_b.set_xticklabels(periods, rotation=20, ha="right", rotation_mode="anchor", fontsize=5.5)
    ax_b.set_yticks(np.arange(len(modalities)))
    ax_b.set_yticklabels([m[0] for m in modalities], fontsize=5.4)
    ax_b.set_xlabel("Five-year clinical periods")
    ax_b.set_title("Evolution of surgical & diagnostic modalities", pad=6)

    max_v = mat.max()
    for r_i in range(mat.shape[0]):
        for c_i in range(mat.shape[1]):
            val = mat[r_i, c_i]
            txt_col = "#FFFFFF" if val > max_v * 0.52 else "#111111"
            ax_b.text(c_i, r_i, str(val), ha="center", va="center", fontsize=5.5, fontweight="bold" if val >= 15 else "normal", color=txt_col)

    add_panel_label(fig, ax_a, "a", dx_pt=-45, dy_pt=6)
    add_panel_label(fig, ax_b, "b", dx_pt=-45, dy_pt=6)

    export_figure(
        fig, "fig7_keyword_bursts",
        row_groups=[["a", "b"]]
    )


def main():
    raw_recs = parse_wos_records(STRICT_PATH)
    records = [parse_fields(r)[0] for r in raw_recs]
    build_fig4_authors_journals(records)
    build_fig5_cocitation_analysis(records)
    build_fig6_keyword_cooccurrence(records)
    build_fig7_keyword_bursts(records)


if __name__ == "__main__":
    main()
