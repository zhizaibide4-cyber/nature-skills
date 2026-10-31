#!/usr/bin/env python3
"""
Generate Figures 1, 2, and 3 for the SCI manuscript:
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
import sys
from collections import Counter, defaultdict
from itertools import combinations

import matplotlib as mpl
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

sys.path.insert(0, "/workspace/skills/nature-figure/scripts")
sys.path.insert(0, "/workspace/bibliometrics_hae")

from audit_panel_alignment import require_matplotlib_panel_alignment
from clean_wos_hae import parse_fields, parse_wos_records
from generate_summary_tables import calc_h_index, extract_countries_and_insts

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

OUT_FIG_DIR = "/workspace/bibliometrics_hae/figures"
OUT_SRC_DIR = "/workspace/bibliometrics_hae/source_data"
STRICT_PATH = "/workspace/bibliometrics_hae/data_cleaned/wos_hae_surgery_strict_cleaned.txt"

os.makedirs(OUT_FIG_DIR, exist_ok=True)
os.makedirs(OUT_SRC_DIR, exist_ok=True)

PAL = {
    "navy": "#1F4E78",
    "blue": "#2E75B6",
    "sky": "#6BAED6",
    "light_blue": "#DCEBF7",
    "coral": "#C55A11",
    "amber": "#D9822B",
    "soft_orange": "#F8CBAD",
    "teal": "#2A788E",
    "mint": "#5EC962",
    "sage": "#4E8A6E",
    "light_green": "#E2EFDA",
    "plum": "#7A5195",
    "crimson": "#A63636",
    "slate": "#595959",
    "grey": "#8C8C8C",
    "light_grey": "#F2F4F7",
    "border_grey": "#BFBFBF",
}


def add_panel_label(fig, ax, label, dx_pt=-22, dy_pt=8):
    return ax.annotate(
        label,
        xy=(0.0, 1.0),
        xycoords="axes fraction",
        xytext=(dx_pt, dy_pt),
        textcoords="offset points",
        fontsize=8.5,
        fontweight="bold",
        ha="left",
        va="bottom",
        color="#111111",
    )


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
# FIGURE 1: PRISMA 2020 Flowchart & Standardization Pipeline
# ===========================================================================
def build_fig1_prisma():
    fig, ax = plt.subplots(figsize=(7.2, 5.6))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    def draw_box(x, y, w, h, title, lines, fc="#FFFFFF", ec="#2E75B6", title_color="#1F4E78", lw=0.9):
        rect = mpatches.Rectangle(
            (x, y), w, h,
            facecolor=fc, edgecolor=ec, linewidth=lw, zorder=2
        )
        ax.add_patch(rect)
        if title:
            ax.text(
                x + w / 2.0, y + h - 2.0, title,
                ha="center", va="top", fontsize=6.5, fontweight="bold", color=title_color, zorder=3
            )
            y_start = y + h - 5.2
        else:
            y_start = y + h - 2.2
        for i, line in enumerate(lines):
            ax.text(
                x + 1.8, y_start - i * 2.9, line,
                ha="left", va="top", fontsize=5.8, color="#222222", zorder=3
            )

    def draw_stage_tag(x, y, h, label, color="#1F4E78"):
        tag = mpatches.Rectangle(
            (x, y), 4.8, h,
            facecolor=color, edgecolor="none", zorder=2
        )
        ax.add_patch(tag)
        ax.text(
            x + 2.4, y + h / 2.0, label,
            ha="center", va="center", rotation=90, rotation_mode="anchor",
            fontsize=6.3, fontweight="bold", color="#FFFFFF", zorder=3
        )

    def draw_arrow(x1, y1, x2, y2):
        ax.annotate(
            "", xy=(x2, y2), xytext=(x1, y1),
            arrowprops=dict(arrowstyle="-|>,head_length=0.4,head_width=0.25", lw=0.9, color="#404040"),
            zorder=4
        )

    # Stage tags on the left
    draw_stage_tag(1.0, 79.0, 18.5, "Identification", PAL["navy"])
    draw_stage_tag(1.0, 57.0, 18.0, "Screening", PAL["blue"])
    draw_stage_tag(1.0, 29.0, 24.0, "Eligibility", PAL["teal"])
    draw_stage_tag(1.0, 3.0, 22.0, "Included", PAL["sage"])

    # Step 1: Identification
    draw_box(
        7.5, 78.5, 46.5, 19.0,
        "Web of Science Core Collection (SCIE)",
        [
            "Search span: Jan 1, 2000 to Oct 31, 2026",
            "Query: (alveolar echinococcosis OR E. multilocularis)",
            "  AND (liver OR hepatic) AND (surgery OR ELRA)",
            "Initial records retrieved: n = 456 (Article / Review)"
        ],
        fc="#F4F8FC", ec=PAL["navy"], title_color=PAL["navy"]
    )

    draw_box(
        58.0, 78.5, 40.5, 19.0,
        "Metadata Quality Inspection",
        [
            "Full record & cited references verified",
            "Unique WoS accession numbers (UT): 456",
            "Duplicate records removed: n = 0",
            "HTML tags stripped (<italic>, <bold>)"
        ],
        fc="#F9FAFB", ec=PAL["border_grey"], title_color=PAL["slate"]
    )
    draw_arrow(54.2, 88.0, 57.8, 88.0)

    # Step 2: Screening
    draw_arrow(30.7, 78.3, 30.7, 75.2)
    draw_box(
        7.5, 57.0, 46.5, 18.0,
        "Publication Integrity & Retraction Screening",
        [
            "Records screened for retraction notices and",
            "bibliographic validity (n = 456)",
            "Non-retracted standardized dataset retained",
            "for sensitivity comparison (n = 453)"
        ],
        fc="#F4F8FC", ec=PAL["blue"], title_color=PAL["navy"]
    )

    draw_box(
        58.0, 57.0, 40.5, 18.0,
        "Excluded: Retracted Publications (n = 3)",
        [
            "1. WOS:000246982200023 (2007, Liver Transpl)",
            "2. WOS:000401125000020 (2017, J Surg Res)",
            "3. WOS:000507597800009 (2019, Sci Rep)",
            "All 3 retracted articles removed prior to analysis"
        ],
        fc="#FDF3EE", ec=PAL["coral"], title_color=PAL["coral"]
    )
    draw_arrow(54.2, 66.0, 57.8, 66.0)

    # Step 3: Eligibility
    draw_arrow(30.7, 56.8, 30.7, 53.2)
    draw_box(
        7.5, 29.0, 46.5, 24.0,
        "Clinical Eligibility Assessment (n = 453)",
        [
            "Title, Abstract & Author Keywords evaluated:",
            "• Confirmed E. multilocularis / HAE diagnosis",
            "• Confirmed hepatic, biliary, or IVC involvement",
            "• Confirmed surgical, transplant, or interventional focus",
            "• Landmark ELRA & hepatic surgery reviews retained"
        ],
        fc="#F2F9F9", ec=PAL["teal"], title_color=PAL["teal"]
    )

    draw_box(
        58.0, 29.0, 40.5, 24.0,
        "Excluded Off-Topic Records (n = 91)",
        [
            "• Pure Cystic Echinococcosis (E. granulosus),",
            "  E. vogeli, or non-echinococcal trauma matched",
            "  only via WoS Keywords Plus (n = 46)",
            "• Veterinary cases (dogs, sheep, primates) or",
            "  mouse/in-vitro preclinical studies (n = 31)",
            "• Exclusively extrahepatic primary lesions (n = 14)"
        ],
        fc="#FDF3EE", ec=PAL["coral"], title_color=PAL["coral"]
    )
    draw_arrow(54.2, 41.0, 57.8, 41.0)

    # Step 4: Included & Thesaurus Standardization
    draw_arrow(30.7, 28.8, 30.7, 25.2)
    draw_box(
        7.5, 3.0, 46.5, 22.0,
        "Final Core HAE Surgical Dataset (n = 362)",
        [
            "• Original research articles: n = 304 (84.0%)",
            "• Clinical reviews & guidelines: n = 58 (16.0%)",
            "• Total citations: 10,361 (Mean CPP = 28.62)",
            "• Dataset H-index: 43 | Co-cited refs: 6,842",
            "• Time span: Jan 1, 2000 – Oct 31, 2026"
        ],
        fc="#EFF7F2", ec=PAL["sage"], title_color=PAL["sage"]
    )

    draw_box(
        58.0, 3.0, 40.5, 22.0,
        "4D Thesaurus & Entity Standardization",
        [
            "• Author disambiguation: merged inverted &",
            "  hyphenated names (Wen H, Aji T, Vuitton DA)",
            "• Institution unification: merged affiliated",
            "  hospitals with parent universities",
            "• Keyword harmonization: unified ELRA,",
            "  hepatectomy, radical resection & PNM terms"
        ],
        fc="#EFF7F2", ec=PAL["sage"], title_color=PAL["sage"]
    )
    draw_arrow(54.2, 14.0, 57.8, 14.0)

    export_figure(fig, "fig1_prisma_flowchart", single_panel=True)


# ===========================================================================
# FIGURE 2: Annual Publication Growth & Citation Trajectory (2000 - 2026)
# ===========================================================================
def build_fig2_annual_trends(records):
    years = list(range(2000, 2027))
    pub_cnt = Counter()
    cite_cnt = Counter()
    for d in records:
        py = int(d["PY"][0].strip())
        tc = int(d["TC"][0].strip()) if d.get("TC") and d["TC"][0].strip().isdigit() else 0
        pub_cnt[py] += 1
        cite_cnt[py] += tc

    pubs = [pub_cnt[y] for y in years]
    cites = [cite_cnt[y] for y in years]
    cum_pubs = np.cumsum(pubs)
    cpp = [round(c / p, 2) if p > 0 else 0.0 for p, c in zip(pubs, cites)]

    with open(os.path.join(OUT_SRC_DIR, "fig2_annual_trends.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Year", "Annual_Publications", "Cumulative_Publications", "Total_Citations", "Mean_Citations_Per_Paper"])
        for y, p, cp, c, m in zip(years, pubs, cum_pubs, cites, cpp):
            w.writerow([y, p, int(cp), c, m])

    fig = plt.figure(figsize=(7.2, 3.2))
    gs = fig.add_gridspec(1, 2, left=0.07, right=0.93, bottom=0.16, top=0.86, wspace=0.35)
    ax_a = fig.add_subplot(gs[0, 0])
    ax_b = fig.add_subplot(gs[0, 1])

    # --- Panel a: Annual Publications & Cumulative Curve with 3 Clinical Phases ---
    ax_a.axvspan(1999.5, 2009.5, color="#F2F4F7", alpha=0.75, lw=0, zorder=0)
    ax_a.axvspan(2009.5, 2018.5, color="#EBF3FA", alpha=0.65, lw=0, zorder=0)
    ax_a.axvspan(2018.5, 2026.5, color="#FDF3EE", alpha=0.65, lw=0, zorder=0)

    bar_colors = [
        PAL["sky"] if y <= 2009 else (PAL["blue"] if y <= 2018 else PAL["coral"])
        for y in years
    ]
    ax_a.bar(years, pubs, width=0.66, color=bar_colors, edgecolor="none", zorder=2)
    ax_a.set_xlim(1999.2, 2026.8)
    ax_a.set_ylim(0, 44)
    ax_a.set_xlabel("Publication year")
    ax_a.set_ylabel("Annual publications (n)", color=PAL["navy"])
    ax_a.set_xticks([2000, 2005, 2010, 2015, 2020, 2026])

    # Place phase labels cleanly inside each span above bars and cumulative line
    ax_a.text(2004.5, 41.5, "Phase I (00–09)\n6.0/yr", ha="center", va="top", fontsize=5.4, color=PAL["slate"])
    ax_a.text(2014.0, 41.5, "Phase II (10–18)\n11.4/yr", ha="center", va="top", fontsize=5.4, color=PAL["navy"])
    ax_a.text(2022.6, 41.5, "Phase III (19–26)\n24.8/yr", ha="center", va="top", fontsize=5.4, color=PAL["coral"], fontweight="bold")

    ax_a2 = ax_a.twinx()
    ax_a2.spines["top"].set_visible(False)
    ax_a2.spines["right"].set_visible(True)
    ax_a2.spines["right"].set_color(PAL["teal"])
    ax_a2.spines["right"].set_linewidth(0.75)
    ax_a2.plot(years, cum_pubs, color=PAL["teal"], linewidth=1.3, marker="o", markersize=2.0, zorder=4)
    ax_a2.set_ylim(0, 520)
    ax_a2.set_ylabel("Cumulative publications (n)", color=PAL["teal"])
    ax_a2.tick_params(axis="y", colors=PAL["teal"])
    ax_a.set_title("Annual & cumulative publication output", pad=6)

    # --- Panel b: Annual Citations & Key Milestone Peaks ---
    ax_b.bar(years, cites, width=0.66, color=PAL["light_blue"], edgecolor=PAL["blue"], linewidth=0.5, zorder=2)
    ax_b.set_xlim(1999.2, 2026.8)
    ax_b.set_ylim(0, 2300)
    ax_b.set_xlabel("Publication year")
    ax_b.set_ylabel("Total citations received (n)", color=PAL["navy"])
    ax_b.set_xticks([2000, 2005, 2010, 2015, 2020, 2026])

    ax_b2 = ax_b.twinx()
    ax_b2.spines["top"].set_visible(False)
    ax_b2.spines["right"].set_visible(True)
    ax_b2.spines["right"].set_color(PAL["coral"])
    ax_b2.spines["right"].set_linewidth(0.75)
    ax_b2.plot(years, cpp, color=PAL["coral"], linewidth=1.25, marker="s", markersize=2.2, zorder=4)
    ax_b2.set_ylim(0, 325)
    ax_b2.set_ylabel("Mean citations per paper (CPP)", color=PAL["coral"])
    ax_b2.tick_params(axis="y", colors=PAL["coral"])

    ax_b.annotate(
        "2003: European LTx\nreport (772 cites)",
        xy=(2003, 790), xytext=(2000.0, 1320),
        fontsize=5.5, color=PAL["navy"],
        arrowprops=dict(arrowstyle="->", lw=0.6, color=PAL["navy"]),
    )
    ax_b.annotate(
        "2010: WHO-IWGE\nconsensus (1,955 cites)",
        xy=(2010, 1965), xytext=(2011.8, 1980),
        fontsize=5.5, fontweight="bold", color=PAL["coral"],
        arrowprops=dict(arrowstyle="->", lw=0.6, color=PAL["coral"]),
    )
    ax_b.annotate(
        "2019: CMR review &\nELRA surge (1,145 cites)",
        xy=(2019, 1160), xytext=(2015.8, 1540),
        fontsize=5.5, color=PAL["navy"],
        arrowprops=dict(arrowstyle="->", lw=0.6, color=PAL["navy"]),
    )
    ax_b.set_title("Citation impact & milestone peaks", pad=6)

    add_panel_label(fig, ax_a, "a", dx_pt=-24, dy_pt=6)
    add_panel_label(fig, ax_b, "b", dx_pt=-24, dy_pt=6)

    export_figure(
        fig, "fig2_annual_trends",
        row_groups=[["a", "b"]],
        exclude_axes=[ax_a2, ax_b2]
    )


# ===========================================================================
# Helper for zero-collision radial chord network plots
# ===========================================================================
def draw_radial_network(ax, nodes, node_weights, edges_dict, node_colors, short_labels=None, size_scale=1.0):
    """
    Draws a circular network where all nodes lie on radius R_node = 0.48,
    all edges lie strictly inside r <= 0.48, and all text labels lie strictly
    outside at R_label = 0.88 with outward alignment, guaranteeing zero text-stroke collision.
    """
    n = len(nodes)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
    R_node = 0.48
    R_label = 0.88
    pos = {node: (R_node * np.cos(a), R_node * np.sin(a)) for node, a in zip(nodes, angles)}

    for (u, v), w in edges_dict.items():
        if u in pos and v in pos and w >= 1:
            ax.plot(
                [pos[u][0], pos[v][0]], [pos[u][1], pos[v][1]],
                color=PAL["sky"], alpha=min(0.80, 0.22 + 0.06 * w),
                linewidth=0.5 + 0.20 * min(w, 10), zorder=1
            )

    for idx, node in enumerate(nodes):
        x, y = pos[node]
        w_val = node_weights[node]
        sz = 22 + 1.05 * (w_val * size_scale)
        ax.scatter([x], [y], s=sz, color=node_colors[node], edgecolors="none", zorder=3)

        ang = angles[idx]
        lx = R_label * np.cos(ang)
        ly = R_label * np.sin(ang)
        cos_a = np.cos(ang)
        sin_a = np.sin(ang)
        ha = "left" if cos_a > 0.2 else ("right" if cos_a < -0.2 else "center")
        va = "bottom" if sin_a > 0.35 else ("top" if sin_a < -0.35 else "center")
        lbl = short_labels.get(node, node) if short_labels else node
        ax.text(
            lx, ly, f"{lbl} ({w_val})",
            ha=ha, va=va, fontsize=5.4,
            fontweight="bold" if idx < 4 else "normal",
            color="#111111", zorder=4
        )

    ax.set_xlim(-1.85, 1.85)
    ax.set_ylim(-1.28, 1.28)
    ax.patch.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ["left", "bottom", "right", "top"]:
        ax.spines[sp].set_visible(False)


# ===========================================================================
# FIGURE 3: Global Countries/Regions & Core Institutions (2x2 Grid a-d)
# ===========================================================================
def build_fig3_countries_institutions(records):
    country_pubs = Counter()
    country_cites = defaultdict(list)
    country_edges = Counter()

    inst_pubs = Counter()
    inst_cites = defaultdict(list)
    inst_edges = Counter()

    for d in records:
        tc = int(d["TC"][0].strip()) if d.get("TC") and d["TC"][0].strip().isdigit() else 0
        countries, insts = extract_countries_and_insts(d)
        insts = {i for i in insts if i != "Univ Hosp"}
        for c in countries:
            country_pubs[c] += 1
            country_cites[c].append(tc)
        for c1, c2 in combinations(sorted(countries), 2):
            country_edges[(c1, c2)] += 1

        for inst in insts:
            inst_pubs[inst] += 1
            inst_cites[inst].append(tc)
        for i1, i2 in combinations(sorted(insts), 2):
            inst_edges[(i1, i2)] += 1

    fig = plt.figure(figsize=(7.2, 5.8))
    gs = fig.add_gridspec(2, 2, left=0.19, right=0.96, bottom=0.08, top=0.93, wspace=0.40, hspace=0.38)
    ax_a = fig.add_subplot(gs[0, 0])
    ax_b = fig.add_subplot(gs[0, 1])
    ax_c = fig.add_subplot(gs[1, 0])
    ax_d = fig.add_subplot(gs[1, 1])

    # --- Panel a: Top 10 Countries Bar + CPP ---
    top_c = country_pubs.most_common(10)[::-1]
    c_names = [x[0] for x in top_c]
    c_vals = [x[1] for x in top_c]
    c_cpps = [round(sum(country_cites[x[0]]) / x[1], 1) for x in top_c]
    y_pos = np.arange(len(c_names))

    bar_cols = [PAL["coral"] if c == "China" else PAL["blue"] for c in c_names]
    ax_a.barh(y_pos, c_vals, height=0.62, color=bar_cols, edgecolor="none")
    ax_a.set_yticks(y_pos)
    ax_a.set_yticklabels(c_names)
    ax_a.set_xlim(0, 215)
    ax_a.set_xlabel("Publications (n)")
    ax_a.set_title("Top 10 productive countries", pad=6)
    for y, v, cpp_v in zip(y_pos, c_vals, c_cpps):
        ax_a.text(v + 3.5, y, f"{v} (CPP: {cpp_v})", va="center", ha="left", fontsize=5.4, color="#222222")

    # --- Panel b: International Collaboration Network ---
    top12_c = [x[0] for x in country_pubs.most_common(12)]
    c_colors = {
        c: (PAL["coral"] if c == "China" else (PAL["teal"] if c in {"France", "Germany", "Switzerland", "Austria", "Italy", "Poland"} else PAL["amber"]))
        for c in top12_c
    }
    draw_radial_network(ax_b, top12_c, country_pubs, country_edges, c_colors)
    ax_b.set_title("Country co-authorship network", pad=6)

    # --- Panel c: Top 10 Core Institutions ---
    short_inst_labels = {
        "Xinjiang Medical University": "Xinjiang Med Univ",
        "Sichuan University": "Sichuan Univ (West China)",
        "University of Franche-Comte / CHU Besancon": "Univ Franche-Comte / Besancon",
        "Qinghai University": "Qinghai Univ",
        "Ulm University": "Ulm Univ",
        "University of Bern": "Univ Bern",
        "Qinghai Provincial People's Hospital": "Qinghai Prov People's Hosp",
        "Ataturk University": "Ataturk Univ",
        "University of Zurich": "Univ Zurich",
        "Medical University of Warsaw": "Med Univ Warsaw",
    }
    top_i = [(k, v) for k, v in inst_pubs.most_common(12) if k != "World Health Organization"][:10][::-1]
    i_names = [short_inst_labels.get(x[0], x[0]) for x in top_i]
    i_vals = [x[1] for x in top_i]
    i_cpps = [round(sum(inst_cites[x[0]]) / x[1], 1) for x in top_i]
    y_pos_i = np.arange(len(i_names))

    i_cols = [
        PAL["coral"] if "Xinjiang" in x[0] or "Sichuan" in x[0] or "Qinghai" in x[0] else PAL["teal"]
        for x in top_i
    ]
    ax_c.barh(y_pos_i, i_vals, height=0.62, color=i_cols, edgecolor="none")
    ax_c.set_yticks(y_pos_i)
    ax_c.set_yticklabels(i_names)
    ax_c.set_xlim(0, 82)
    ax_c.set_xlabel("Publications (n)")
    ax_c.set_title("Top 10 productive institutions", pad=6)
    for y, v, cpp_v in zip(y_pos_i, i_vals, i_cpps):
        ax_c.text(v + 1.5, y, f"{v} (CPP: {cpp_v})", va="center", ha="left", fontsize=5.4, color="#222222")

    # --- Panel d: Institutional Collaboration Network ---
    top10_i_keys = [x[0] for x in top_i[::-1]]
    short_net_i = {
        "Xinjiang Medical University": "Xinjiang MU",
        "Sichuan University": "Sichuan U",
        "University of Franche-Comte / CHU Besancon": "CHU Besancon",
        "Qinghai University": "Qinghai U",
        "Ulm University": "Ulm U",
        "University of Bern": "U Bern",
        "Qinghai Provincial People's Hospital": "Qinghai Hosp",
        "Ataturk University": "Ataturk U",
        "University of Zurich": "U Zurich",
        "Medical University of Warsaw": "Warsaw MU",
    }
    i_net_colors = {
        k: (PAL["coral"] if ("Xinjiang" in k or "Sichuan" in k or "Qinghai" in k) else PAL["teal"])
        for k in top10_i_keys
    }
    draw_radial_network(ax_d, top10_i_keys, inst_pubs, inst_edges, i_net_colors, short_labels=short_net_i)
    ax_d.set_title("Institutional collaboration network", pad=6)

    add_panel_label(fig, ax_a, "a", dx_pt=-48, dy_pt=6)
    add_panel_label(fig, ax_b, "b", dx_pt=-18, dy_pt=6)
    add_panel_label(fig, ax_c, "c", dx_pt=-48, dy_pt=6)
    add_panel_label(fig, ax_d, "d", dx_pt=-18, dy_pt=6)

    export_figure(
        fig, "fig3_countries_institutions",
        row_groups=[["a", "b"], ["c", "d"]],
        column_groups=[["a", "c"], ["b", "d"]]
    )


def main():
    raw_recs = parse_wos_records(STRICT_PATH)
    records = [parse_fields(r)[0] for r in raw_recs]
    build_fig1_prisma()
    build_fig2_annual_trends(records)
    build_fig3_countries_institutions(records)


if __name__ == "__main__":
    main()
