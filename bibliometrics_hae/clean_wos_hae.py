#!/usr/bin/env python3
"""
Reproducible Data Cleaning and Standardization Pipeline for Bibliometric Analysis of
Surgical Treatment of Hepatic Alveolar Echinococcosis (HAE) (2000 - Oct 31, 2026).

Generates:
1. data_cleaned/wos_hae_surgery_strict_cleaned.txt (PRISMA-filtered core clinical HAE surgical dataset)
2. data_cleaned/wos_hae_surgery_full453_cleaned.txt (All 453 non-retracted records, fully standardized)
3. thesaurus/thesaurus_authors.txt (VOSviewer author disambiguation file)
4. thesaurus/thesaurus_keywords.txt (VOSviewer keyword standardization file)
5. thesaurus/thesaurus_organizations.txt (VOSviewer institution standardization file)
6. thesaurus/thesaurus_countries.txt (VOSviewer country standardization file)
7. tables/prisma_exclusion_log.csv (Detailed PRISMA screening exclusion log)
8. tables/summary_tables.md (Publication-ready tables for the SCI manuscript)
"""

import csv
import os
import re
from collections import Counter, defaultdict

RAW_PATH = "/home/ubuntu/.cursor/projects/workspace/uploads/savedrecs__6__1035.txt"
OUT_DIR = "/workspace/bibliometrics_hae"


# ---------------------------------------------------------------------------
# 1. Author Standardization Dictionary (AF and AU)
#    Verified against institutional affiliations (C1/RP) and ORCIDs
# ---------------------------------------------------------------------------
AUTHOR_AF_MAP = {
    # Xinjiang Medical University core team
    "Aji, Tuerganaili": "Aji, Tuerganaili",
    "AJi, Tuerganaili": "Aji, Tuerganaili",
    "Aji, Tuerganali": "Aji, Tuerganaili",
    "Aji, T.": "Aji, Tuerganaili",
    "Aji, T": "Aji, Tuerganaili",
    "Tuerganaili, Aji": "Aji, Tuerganaili",
    "Tuergan, Aili": "Aji, Tuerganaili",
    "Aili, Tuergan": "Aji, Tuerganaili",
    "Wen, Hao": "Wen, Hao",
    "Wen Hao": "Wen, Hao",
    "Wen, H.": "Wen, Hao",
    "Wen, H": "Wen, Hao",
    "Hao, Wen": "Wen, Hao",
    "Shao, Yingmei": "Shao, Yingmei",
    "Shao, Ying-Mei": "Shao, Yingmei",
    "Shao, Ying-mei": "Shao, Yingmei",
    "Shao Ying-mei": "Shao, Yingmei",
    "Shao, Y. -M.": "Shao, Yingmei",
    "Shao, Y.": "Shao, Yingmei",
    "Jiang, Tiemin": "Jiang, Tiemin",
    "Jiang, Tie-Min": "Jiang, Tiemin",
    "Jiang, Tie-min": "Jiang, Tiemin",
    "Jiang, Tieming": "Jiang, Tiemin",
    "Jiang, T.": "Jiang, Tiemin",
    "Ran, Bo": "Ran, Bo",
    "Ran, B.": "Ran, Bo",
    "Bo, Ran": "Ran, Bo",
    "Zhang, Ruiqing": "Zhang, Ruiqing",
    "Zhang, Rui-Qing": "Zhang, Ruiqing",
    "Zhang, Rui-qing": "Zhang, Ruiqing",
    "Zhang, R.": "Zhang, Ruiqing",
    "Guo, Qiang": "Guo, Qiang",
    "Guo, Q.": "Guo, Qiang",
    "Tuxun, Tuerhongjiang": "Tuxun, Tuerhongjiang",
    "Tuxun Tuer-hongjiang": "Tuxun, Tuerhongjiang",
    "Tuxun, T.": "Tuxun, Tuerhongjiang",
    "Zhao, Jin-Ming": "Zhao, Jinming",
    "Zhao, Jin-ming": "Zhao, Jinming",
    "Zhao Jin-ming": "Zhao, Jinming",
    "Zhao, J. -M.": "Zhao, Jinming",
    "Zhao, Jinming": "Zhao, Jinming",
    "Lin, Ren-Yong": "Lin, Renyong",
    "Lin, Renyong": "Lin, Renyong",
    "Liu, Wen-Ya": "Liu, Wenya",
    "Liu, Wen-ya": "Liu, Wenya",
    "Liu, Wenya": "Liu, Wenya",
    "Wang, Mao-Lin": "Wang, Maolin",
    "Wang, Maolin": "Wang, Maolin",
    "Ahan, Ayifuhan": "Ahan, Ayifuhan",
    "Ayifuhan, Ahan": "Ahan, Ayifuhan",
    "Zhang, Jin-Hui": "Zhang, Jinhui",
    "Zhang, Jin-hui": "Zhang, Jinhui",
    "Zhang Jin-hui": "Zhang, Jinhui",
    "Zhang, J. -H.": "Zhang, Jinhui",
    "Ji, Xuewen": "Ji, Xuewen",
    "Ji, Xue-wen": "Ji, Xuewen",
    "Ji Xue-wen": "Ji, Xuewen",
    "Ji, X. -W.": "Ji, Xuewen",
    "Tai, Qin-wen": "Tai, Qinwen",
    "Tai Qin-wen": "Tai, Qinwen",
    "Tai, Q. -W.": "Tai, Qinwen",
    "Li Tao": "Li, Tao",
    "Li, T.": "Li, Tao",
    "He, Yi-Biao": "He, Yibiao",
    "He, Yi-biao": "He, Yibiao",
    "Qin, Yongde": "Qin, Yongde",
    "Qin, Yong-De": "Qin, Yongde",
    "Lu, Xiao-Mei": "Lu, Xiaomei",
    "Lu, Xiaomei": "Lu, Xiaomei",
    "Zan, Run-Na": "Zan, Runna",
    "Zan, Runna": "Zan, Runna",

    # Sichuan University (West China Hospital) & Tsinghua University core team
    "Wang, Wentao": "Wang, Wentao",
    "Wang, WenTao": "Wang, Wentao",
    "Wang, Wen-Tao": "Wang, Wentao",
    "Wang, Wen-tao": "Wang, Wentao",
    "Wang Wentao": "Wang, Wentao",
    "Wang Wen-tao": "Wang, Wentao",
    "Wang, WT": "Wang, Wentao",
    "Yan, Lunan": "Yan, Lunan",
    "Yan, Lu-nan": "Yan, Lunan",
    "Yan, Lv-Nan": "Yan, Lunan",
    "Yan, LN": "Yan, Lunan",
    "Yan, Lunang": "Yan, Lunan",
    "Yan Lunan": "Yan, Lunan",
    "Yan Lue-nan": "Yan, Lunan",
    "Yang, Jia-Yin": "Yang, Jiayin",
    "Yang, Jiayin": "Yang, Jiayin",
    "Yang, Jia-yin": "Yang, Jiayin",
    "Yang Jia-yin": "Yang, Jiayin",
    "Yang, JY": "Yang, Jiayin",
    "Wen, Tianfu": "Wen, Tianfu",
    "Wen, Tian-fu": "Wen, Tianfu",
    "Wen Tian-fu": "Wen, Tianfu",
    "Wen, TF": "Wen, Tianfu",
    "Wen, Tingfu": "Wen, Tianfu",
    "Chen, Zheyu": "Chen, Zheyu",
    "Chen, Zhe-yu": "Chen, Zheyu",
    "Chen, Zhe-Yu": "Chen, Zheyu",
    "Chen Zhe-yu": "Chen, Zheyu",
    "Xu, Mingqing": "Xu, Mingqing",
    "Xu, Ming-qing": "Xu, Mingqing",
    "Xu Ming-qing": "Xu, Mingqing",
    "Xu Mingqing": "Xu, Mingqing",
    "Wei, Yong-gang": "Wei, Yonggang",
    "Wei, Yonggang": "Wei, Yonggang",
    "Huang, Ji-wei": "Huang, Jiwei",
    "Huang, Jiwei": "Huang, Jiwei",
    "Li, Jia-xin": "Li, Jiaxin",
    "Li, Jia-Xin": "Li, Jiaxin",
    "Chen, Ke-fei": "Chen, Kefei",
    "Chen, Ke-Fei": "Chen, Kefei",
    "Cai, Di-Ming": "Cai, Diming",
    "Cai, Diming": "Cai, Diming",
    "Li, Yong-Zhong": "Li, Yongzhong",
    "Li, Yongzhong": "Li, Yongzhong",
    "Zhou, Rong-Xing": "Zhou, Rongxing",
    "Zhou, Rongxing": "Zhou, Rongxing",
    "Dong, Jia-Hong": "Dong, Jiahong",
    "Dong, Jiahong": "Dong, Jiahong",
    "Dong Jia-hong": "Dong, Jiahong",
    "Dong, J. -H.": "Dong, Jiahong",
    "Duan Wei-dong": "Duan, Weidong",
    "Duan, W. -D.": "Duan, Weidong",
    "Liang Yu-rong": "Liang, Yurong",
    "Liang, Y. -R.": "Liang, Yurong",
    "Lei Jianyong": "Lei, Jianyong",
    "Hao Jingcheng": "Hao, Jingcheng",
    "Zhao Jichun": "Zhao, Jichun",
    "Zhao Ji-chun": "Zhao, Jichun",
    "Huang Bing": "Huang, Bin",
    "Yuan Ding": "Yuan, Ding",
    "Zeng Yong": "Zeng, Yong",
    "Li Bo": "Li, Bo",
    "Li, B": "Li, Bo",

    # Qinghai University core team
    "Fan, Haining": "Fan, Haining",
    "Fan, Hai-Ning": "Fan, Haining",
    "Fan, Hai-ning": "Fan, Haining",
    "Wang, Haijiu": "Wang, Haijiu",
    "Wang, Hai-Jiu": "Wang, Haijiu",
    "Wang, Hai-jiu": "Wang, Haijiu",
    "Wang, Zhixin": "Wang, Zhixin",
    "Wang, Zhi-xin": "Wang, Zhixin",
    "Zhu, Hai-Hong": "Zhu, Haihong",
    "Zhu, Haihong": "Zhu, Haihong",
    "Zhu, H.": "Zhu, Haihong",
    "Hou, Lizhao": "Hou, Lizhao",
    "Hou, Li-Zhao": "Hou, Lizhao",
    "Chai, Jinping": "Chai, Jinping",
    "Chai, Jin-Ping": "Chai, Jinping",
    "Zhao, Shunyun": "Zhao, Shunyun",
    "Zhao, Shun-Yun": "Zhao, Shunyun",
    "Zhang, Ling-Qiang": "Zhang, Lingqiang",
    "Zhang, Ling-qiang": "Zhang, Lingqiang",
    "Zhang, Lingqiang": "Zhang, Lingqiang",
    "Liu, Lin-Xun": "Liu, Linxun",
    "Liu, Lin-xun": "Liu, Linxun",
    "Wang, Xiao-Song": "Wang, Xiaosong",
    "Wang, Xiaosong": "Wang, Xiaosong",
    "Feng, Jian-Guo": "Feng, Jianguo",
    "Feng, Jianguo": "Feng, Jianguo",

    # European & International core teams
    "Vuitton, DA": "Vuitton, Dominique Angele",
    "Vuitton, D. A.": "Vuitton, Dominique Angele",
    "Vuitton, Dominique A.": "Vuitton, Dominique Angele",
    "Vuitton, Dominique Angele": "Vuitton, Dominique Angele",
    "Vuitton, Dominique-Angele": "Vuitton, Dominique Angele",
    "Bresson-Hadni, Solange": "Bresson-Hadni, Solange",
    "Bresson-Hadni, S": "Bresson-Hadni, Solange",
    "Gottstein, Bruno": "Gottstein, Bruno",
    "Gottstein, B": "Gottstein, Bruno",
    "Gottstein, B.": "Gottstein, Bruno",
    "Kern, Peter": "Kern, Peter",
    "Kern, P": "Kern, Peter",
    "Kern, P.": "Kern, Peter",
    "Barth, Thomas F. E.": "Barth, Thomas F. E.",
    "Barth, Thomas E. E.": "Barth, Thomas F. E.",
    "Barth, Thomas F.": "Barth, Thomas F. E.",
    "Barth, Thomas Fe": "Barth, Thomas F. E.",
    "Wang, Jun-Hua": "Wang, Junhua",
    "Wang, Junhua": "Wang, Junhua",
    "Mantion, Georges A.": "Mantion, Georges A.",
    "Mantion, Georges": "Mantion, Georges A.",
    "Mantion, G": "Mantion, Georges A.",
    "Mantion, GA": "Mantion, Georges A.",
    "Mantion, Georges Andre": "Mantion, Georges A.",
    "Blagosklonov, Oleg": "Blagosklonov, Oleg",
    "Blagosklonov, O": "Blagosklonov, Oleg",
    "Delabrousse, Eric": "Delabrousse, Eric",
    "Delabrousse, E": "Delabrousse, Eric",
    "Deplazes, Peter": "Deplazes, Peter",
    "Deplazes, P": "Deplazes, Peter",
    "Hemphill, Andrew": "Hemphill, Andrew",
    "Hemphill, A": "Hemphill, Andrew",
    "Ito, Akira": "Ito, Akira",
    "Ito, A": "Ito, Akira",
    "Buttenschoen, Klaus": "Buttenschoen, Klaus",
    "Buttenschoen, K": "Buttenschoen, Klaus",
    "Reuter, Stefan": "Reuter, Stefan",
    "Reuter, S": "Reuter, Stefan",
    "Akhan, Okan": "Akhan, Okan",
    "Akhan, O": "Akhan, Okan",
    "Akhan, O.": "Akhan, Okan",
    "Ozturk, Gurkan": "Ozturk, Gurkan",
    "Ozturk, G.": "Ozturk, Gurkan",
    "Craig, Philip S.": "Craig, Philip S.",
    "Craig, PS": "Craig, Philip S.",
    "Craig, P": "Craig, Philip S.",
    "McManus, Donald P.": "McManus, Donald P.",
    "McManus, DP": "McManus, Donald P.",
    "McManus, D. P.": "McManus, Donald P.",
}

AUTHOR_AU_MAP = {
    "Tuerganaili, A": "Aji, T",
    "Tuergan, A": "Aji, T",
    "Aili, T": "Aji, T",
    "AJi, T": "Aji, T",
    "Hao, W": "Wen, H",
    "Bo, R": "Ran, B",
    "Ayifuhan, A": "Ahan, A",
    "Shao, Y": "Shao, YM",
    "Jiang, T": "Jiang, TM",
    "Tuxun, TH": "Tuxun, T",
    "Vuitton, D": "Vuitton, DA",
    "Mantion, G": "Mantion, GA",
    "Craig, P": "Craig, PS",
}

# ---------------------------------------------------------------------------
# 2. Keyword Standardization Dictionary (DE & ID)
# ---------------------------------------------------------------------------
KEYWORD_MAP = {
    # Disease terminology
    "alveolar echinococcosis": "alveolar echinococcosis",
    "alveolar echinococcosis (ae)": "alveolar echinococcosis",
    "human alveolar echinococcosis": "alveolar echinococcosis",
    "alveolar hydatid disease": "alveolar echinococcosis",
    "alveolar hydatid": "alveolar echinococcosis",
    "alveolar hydatid cyst": "alveolar echinococcosis",
    "alveolar hydatidosis": "alveolar echinococcosis",
    "alveococcosis": "alveolar echinococcosis",
    "hepatic alveolar echinococcosis": "hepatic alveolar echinococcosis",
    "hepatic alveolar echinococcosis (hae)": "hepatic alveolar echinococcosis",
    "liver alveolar echinococcosis": "hepatic alveolar echinococcosis",
    "hepatic alveolar hydatid cyst": "hepatic alveolar echinococcosis",
    "hepatic alveolar hydatid disease": "hepatic alveolar echinococcosis",
    "liver alveococcosis": "hepatic alveolar echinococcosis",
    "echinococcus multilocularis": "echinococcus multilocularis",
    "e. multilocularis": "echinococcus multilocularis",
    "e-multilocularis": "echinococcus multilocularis",
    "echinococcus alveolaris": "echinococcus multilocularis",
    "echinococcosis multilocularis": "echinococcus multilocularis",
    "multilocularis": "echinococcus multilocularis",
    "multilocularis infection": "echinococcus multilocularis",
    "fox tapeworm": "echinococcus multilocularis",
    "echinococcus granulosus": "echinococcus granulosus",
    "e. granulosus": "echinococcus granulosus",
    "granulosus": "echinococcus granulosus",
    "cystic echinococcosis": "cystic echinococcosis",
    "human cystic echinococcosis": "cystic echinococcosis",
    "hydatid-disease": "hydatid disease",
    "hydatidosis": "hydatid disease",
    "hydatid cyst": "hydatid disease",
    "hydatid cysts": "hydatid disease",
    "hydatid": "hydatid disease",
    "echinococciasis": "echinococcosis",
    "echinococcus": "echinococcosis",

    # Surgical techniques & transplantation
    "ex vivo liver resection and autotransplantation": "ex vivo liver resection and autotransplantation",
    "ex vivo liver resection and autotransplantation (elra)": "ex vivo liver resection and autotransplantation",
    "elra": "ex vivo liver resection and autotransplantation",
    "ex vivo liver resection": "ex vivo liver resection and autotransplantation",
    "ex-vivo liver resection": "ex vivo liver resection and autotransplantation",
    "ex-situ ex-vivo liver resection": "ex vivo liver resection and autotransplantation",
    "vivo liver resection": "ex vivo liver resection and autotransplantation",
    "ex vivo resection": "ex vivo liver resection and autotransplantation",
    "ex vivo": "ex vivo liver resection and autotransplantation",
    "liver autotransplantation": "ex vivo liver resection and autotransplantation",
    "autologous liver transplantation": "ex vivo liver resection and autotransplantation",
    "autotransplantation": "ex vivo liver resection and autotransplantation",
    "extracorporeal hepatic resection": "ex vivo liver resection and autotransplantation",
    "liver-transplantation": "liver transplantation",
    "orthotopic liver-transplantation": "liver transplantation",
    "orthotopic liver transplantation": "liver transplantation",
    "allogeneic liver transplantation": "liver transplantation",
    "living donor liver transplantation": "living donor liver transplantation",
    "living donor": "living donor liver transplantation",
    "donor liver-transplantation": "living donor liver transplantation",
    "living-donor liver-transplantation": "living donor liver transplantation",
    "hepatectomy": "hepatectomy",
    "liver resection": "hepatectomy",
    "hepatic resection": "hepatectomy",
    "major liver resection": "hepatectomy",
    "resection": "hepatectomy",
    "radical hepatectomy": "radical resection",
    "radical resection": "radical resection",
    "radical surgery": "radical resection",
    "curative resection": "radical resection",
    "r0 resection": "radical resection",
    "palliative surgery": "palliative surgery",
    "palliative resection": "palliative surgery",
    "palliative treatment": "palliative surgery",
    "surgical-treatment": "surgical treatment",
    "surgery": "surgical treatment",
    "liver surgery": "surgical treatment",
    "surgical procedures": "surgical treatment",
    "surgical management": "surgical treatment",
    "surgical intervention": "surgical treatment",
    "operative treatment": "surgical treatment",
    "laparoscopic surgery": "laparoscopic hepatectomy",
    "laparoscopy": "laparoscopic hepatectomy",
    "laparoscopic hepatectomy": "laparoscopic hepatectomy",
    "laparoscopic liver resection": "laparoscopic hepatectomy",
    "inferior vena-cava": "inferior vena cava",
    "inferior vena cava": "inferior vena cava",
    "retrohepatic inferior vena cava": "inferior vena cava",
    "vena-cava": "inferior vena cava",
    "ivc resection": "vascular reconstruction",
    "vascular reconstruction": "vascular reconstruction",
    "reconstruction": "vascular reconstruction",
    "budd-chiari syndrome": "budd-chiari syndrome",
    "budd chiary syndrome": "budd-chiari syndrome",
    "budd-chiari-syndrome": "budd-chiari syndrome",

    # Imaging, Diagnosis, Chemotherapy & Follow-up
    "computed tomography": "computed tomography",
    "computed-tomography": "computed tomography",
    "ct": "computed tomography",
    "magnetic resonance imaging": "magnetic resonance imaging",
    "magnetic-resonance-imaging": "magnetic resonance imaging",
    "mri": "magnetic resonance imaging",
    "ultrasound": "ultrasonography",
    "ultrasonography": "ultrasonography",
    "contrast-enhanced ultrasound": "contrast-enhanced ultrasound",
    "positron-emission-tomography": "pet/ct",
    "positron emission tomography": "pet/ct",
    "fdg-pet/ct": "pet/ct",
    "18f-fdg pet/ct": "pet/ct",
    "pet/ct": "pet/ct",
    "pet-ct": "pet/ct",
    "3d reconstruction": "three-dimensional reconstruction",
    "three-dimensional reconstruction": "three-dimensional reconstruction",
    "albendazole": "albendazole",
    "benzimidazoles": "benzimidazoles",
    "benzimidazole": "benzimidazoles",
    "mebendazole": "mebendazole",
    "chemotherapy": "antiparasitic therapy",
    "drug treatment": "antiparasitic therapy",
    "medical treatment": "antiparasitic therapy",
    "medical-treatment": "antiparasitic therapy",
    "follow-up": "follow-up",
    "term-follow-up": "follow-up",
    "long-term follow-up": "follow-up",
    "complications": "postoperative complications",
    "postoperative complications": "postoperative complications",
    "biliary complication": "biliary complications",
    "biliary complications": "biliary complications",
    "clinical-features": "clinical features",
    "pnm classification": "pnm classification",
}

# ---------------------------------------------------------------------------
# 3. Institution & Country Standardization Dictionaries
# ---------------------------------------------------------------------------
INSTITUTION_MAP = {
    "Xinjiang Med Univ": "Xinjiang Medical University",
    "First Affiliated Hospital of Xinjiang Medical University": "Xinjiang Medical University",
    "Xinjiang Medical University": "Xinjiang Medical University",
    "Sichuan Univ": "Sichuan University",
    "West China Hospital": "Sichuan University",
    "Sichuan University": "Sichuan University",
    "Qinghai Univ": "Qinghai University",
    "Qinghai University": "Qinghai University",
    "Qinghai Prov Peoples Hosp": "Qinghai Provincial People's Hospital",
    "Univ Bern": "University of Bern",
    "University of Bern": "University of Bern",
    "Univ Franche Comte": "University of Franche-Comte / CHU Besancon",
    "Univ Bourgogne Franche Comte": "University of Franche-Comte / CHU Besancon",
    "Univ Hosp Besancon": "University of Franche-Comte / CHU Besancon",
    "Universite Marie et Louis Pasteur": "University of Franche-Comte / CHU Besancon",
    "CHU Besancon": "University of Franche-Comte / CHU Besancon",
    "Univ Ulm": "Ulm University",
    "Univ Hosp Ulm": "Ulm University",
    "Ulm University": "Ulm University",
    "Univ Zurich": "University of Zurich",
    "University of Zurich": "University of Zurich",
    "University Zurich Hospital": "University of Zurich",
    "Ataturk Univ": "Ataturk University",
    "Ataturk University": "Ataturk University",
    "Med Univ Warsaw": "Medical University of Warsaw",
    "Medical University of Warsaw": "Medical University of Warsaw",
    "Univ Alberta": "University of Alberta",
    "University of Alberta": "University of Alberta",
    "Hacettepe Univ": "Hacettepe University",
    "Hacettepe University": "Hacettepe University",
}

COUNTRY_MAP = {
    "Peoples R China": "China",
    "China": "China",
    "England": "United Kingdom",
    "Scotland": "United Kingdom",
    "Wales": "United Kingdom",
    "North Ireland": "United Kingdom",
    "United Kingdom": "United Kingdom",
    "Turkiye": "Turkey",
    "Turkey": "Turkey",
    "USA": "USA",
}


def parse_wos_records(filepath):
    with open(filepath, "r", encoding="utf-8-sig") as f:
        content = f.read()
    raw_chunks = content.split("\nER\n")
    records = []
    for chunk in raw_chunks:
        if "PT " in chunk and ("TI " in chunk or "UT " in chunk):
            records.append(chunk)
    return records


def parse_fields(rec_text):
    data = defaultdict(list)
    ordered_tags = []
    curr_tag = None
    for line in rec_text.splitlines():
        if not line.strip():
            continue
        if line.startswith("FN ") or line.startswith("VR "):
            continue
        tag = line[:2]
        val = line[3:] if len(line) > 3 else ""
        if tag != "  " and re.match(r"^[A-Z0-9]{2}$", tag):
            curr_tag = tag
            if curr_tag not in ordered_tags:
                ordered_tags.append(curr_tag)
            data[curr_tag].append(val)
        elif tag == "  " and curr_tag:
            data[curr_tag].append(val)
    return data, ordered_tags


def clean_html_entities(text):
    # Remove HTML tags such as <italic>, </italic>, <bold>, </bold>, <sub>, <sup>
    text = re.sub(r"</?(?:italic|bold|sub|sup|i|b|u|p|span)[^>]*>", "", text, flags=re.I)
    # Fix broken entity in WOS:001605718300001 ("Baden-W & uuml;rttemberg")
    text = re.sub(r"&\s*uuml;", "u", text)
    text = re.sub(r"&\s*auml;", "a", text)
    text = re.sub(r"&\s*ouml;", "o", text)
    return text


def standardize_author_af(name):
    name_s = name.strip()
    if name_s in AUTHOR_AF_MAP:
        return AUTHOR_AF_MAP[name_s]
    # If missing comma in Chinese 2-part name (e.g. "Song Tao" -> "Song, Tao")
    if "," not in name_s and name_s != "[Anonymous]":
        parts = name_s.split()
        if len(parts) == 2:
            candidate = f"{parts[0]}, {parts[1].capitalize()}"
            return AUTHOR_AF_MAP.get(candidate, candidate)
    # Normalize hyphenated Chinese given names in "Last, First-Second" -> "Last, Firstsecond"
    if "," in name_s:
        last, first = [x.strip() for x in name_s.split(",", 1)]
        if re.match(r"^[A-Z][a-z]+-[A-Za-z]+$", first) and last in {
            "Wang", "Li", "Zhang", "Liu", "Chen", "Yang", "Huang", "Zhao", "Wu", "Zhou",
            "Xu", "Sun", "Ma", "Zhu", "Hu", "Guo", "He", "Gao", "Lin", "Luo", "Zheng",
            "Liang", "Xie", "Song", "Tang", "Xu", "Deng", "Feng", "Cao", "Peng", "Zeng",
            "Xiao", "Tian", "Dong", "Yuan", "Pan", "Yu", "Jiang", "Cai", "Jia", "Ding",
            "Wei", "Shen", "Ren", "Lu", "Yao", "zhong", "Shao", "Fan", "Yan", "Wen",
            "Qin", "Chai", "Hou", "Zan", "Shang", "Du", "Lv", "Wan"
        }:
            merged_first = first.replace("-", "").capitalize()
            candidate = f"{last}, {merged_first}"
            return AUTHOR_AF_MAP.get(candidate, candidate)
    return name_s


def standardize_author_au(name, af_standardized=None):
    name_s = name.strip()
    if name_s in AUTHOR_AU_MAP:
        return AUTHOR_AU_MAP[name_s]
    if af_standardized and "," in af_standardized:
        last, first = [x.strip() for x in af_standardized.split(",", 1)]
        # For key disambiguated authors, enforce consistent AU
        if af_standardized == "Aji, Tuerganaili":
            return "Aji, T"
        if af_standardized == "Wen, Hao":
            return "Wen, H"
        if af_standardized == "Shao, Yingmei":
            return "Shao, YM"
        if af_standardized == "Jiang, Tiemin":
            return "Jiang, TM"
        if af_standardized == "Wang, Wentao":
            return "Wang, WT"
        if af_standardized == "Fan, Haining":
            return "Fan, HN"
        if af_standardized == "Vuitton, Dominique Angele":
            return "Vuitton, DA"
        if af_standardized == "Bresson-Hadni, Solange":
            return "Bresson-Hadni, S"
        if af_standardized == "Gottstein, Bruno":
            return "Gottstein, B"
        if af_standardized == "Kern, Peter":
            return "Kern, P"
    return name_s


def standardize_keywords(kw_lines):
    raw_text = clean_html_entities(" ".join(kw_lines))
    raw_kws = [x.strip() for x in raw_text.split(";") if x.strip()]
    cleaned = []
    seen = set()
    for kw in raw_kws:
        kw_low = re.sub(r"\s+", " ", kw.lower()).strip()
        mapped = KEYWORD_MAP.get(kw_low, kw_low)
        if mapped not in seen:
            seen.add(mapped)
            cleaned.append(mapped)
    return "; ".join(cleaned)


def classify_record_for_prisma(data):
    """
    Returns (keep_in_strict: bool, exclusion_category: str, exclusion_detail: str)
    Categories:
      - Included: Core human HAE surgical/clinical management literature
      - Excluded_Retracted: Retracted publication (n=3)
      - Excluded_OffTopic_CE_or_Other: Pure Cystic Echinococcosis (CE), E. vogeli, or non-echinococcal disease matched only via Keywords Plus (n=37)
      - Excluded_Veterinary_or_Preclinical: Pure veterinary cases (dogs/foxes/primates/sheep/chinchilla) or mouse/in vitro basic experimental studies without human surgical focus (n=24)
    """
    ut = data["UT"][0].strip()
    dt = " ".join(data["DT"]).strip()
    ti = clean_html_entities(" ".join(data["TI"]).strip())
    ab = clean_html_entities(" ".join(data["AB"]).strip())
    de = clean_html_entities(" ".join(data["DE"]).strip())
    tiabde = f"{ti} {ab} {de}"

    # 1. Retracted publications
    if "Retracted" in dt or "Withdrawn" in ti or ti.startswith("RETRACTED:"):
        return False, "Excluded_Retracted", "Retracted publication in Web of Science"

    # 2. Pure veterinary or preclinical animal/in-vitro studies
    vet_or_mouse_ti = re.search(
        r"\b(in\s+a\s+dog|in\s+dogs|four\s+dogs|11-month-old\s+dog|in\s+mice|balb/c\s+mice|"
        r"mouse\s+model|in\s+inbred\s+rats|nonhuman\s+primates|in\s+sheep|chinchilla|"
        r"veterinary\s+aspects\s+of\s+alveolar\s+echinococcosis|"
        r"in\s+vitro\s+parasiticidal|in\s+vitro\s+evaluation\s+of\s+nigella|"
        r"destructive\s+effect\s+of\s+gamma\s+irradiation|plga-peg-cooh\s+nanoparticles|"
        r"oral\s+delivery\s+of\s+anti-parasitic\s+agent-loaded\s+plga\s+nanoparticles|"
        r"suppressive\s+effect\s+of\s+pseudolaric\s+acid\s+b|repurposing\s+niclosamide|"
        r"evaluation\s+of\s+kinase-inhibitors|maca\s+against\s+echinococcosis|"
        r"deletion\s+of\s+fibrinogen-like\s+protein\s+2|immunotherapy\s+of\s+alveolar\s+echinococcosis\s+via\s+pd-1)\b",
        ti,
        re.I,
    )
    if vet_or_mouse_ti:
        return False, "Excluded_Veterinary_or_Preclinical", "Veterinary study or preclinical animal/in-vitro experimental study"

    # 2b. Exclusively extrahepatic organ focus (without hepatic surgical management) or pure allergy/nephrology
    extrahepatic_exclude_uts = {
        "WOS:000183242900025",  # Pulmonary echinococcosis
        "WOS:000176500300010",  # Hydatid lung disease (echinococcosis/hydatidosis)
        "WOS:000221850400003",  # Echinocloccosis and allergy
        "WOS:000643354100001",  # Alveolar Echinococcosis of the Parotid Gland
        "WOS:001838546300001",  # Primary splenic Alveolar Echinococcosis
        "WOS:000265398600004",  # Surgical management of splenic echinococcal disease
        "WOS:000323419000015",  # Extrahepatic Primary Adrenal Alveolar Echinococcosis
        "WOS:001715446100031",  # Left adrenal echinococcosis misdiagnosed as a left renal cyst
        "WOS:000722532100006",  # Cardiac Alveolar Echinococcosis
        "WOS:000295038600006",  # Mesangioproliferative Glomerulonephritis Secondary to E. alveolaris
        "WOS:000282035100006",  # Medically treated multiple cerebral hydatid cyst disease
        "WOS:001159236500008",  # Cerebral echinococcus that can be confused with brain tumour
        "WOS:000748345400020",  # Perfusion-Weighted MRI of Cerebral Alveolar Echinococcosis
        "WOS:000449373500002",  # 18F-FDG PET/CT imaging of cerebral alveolar echinococcosis
    }
    if ut in extrahepatic_exclude_uts:
        return False, "Excluded_Extrahepatic_Only", "Exclusively extrahepatic organ lesion or non-surgical immunological topic"

    # 3. Check if AE / multilocularis or ELRA/autotransplantation for HAE is present in TI/AB/DE
    ae_pat = re.compile(
        r"(alveolar\s*echinococc\w*|alveolar\s*hydatid\w*|echinococcus\s*multilocularis|"
        r"e\.\s*multilocularis|e-multilocularis|multilocular\s*echinococc\w*|"
        r"multilocular\s*hydatid\w*|echinococcus\s*alveolaris|alveococcosis|\bhae\b)",
        re.I,
    )
    # Explicitly keep landmark ELRA / liver autotransplantation / general hepatic echinococcosis surgery reviews
    keep_landmark_uts = {
        "WOS:001426395500001",  # Aini A, Lu Q, Wen H (2025) Particular Chinese contributions to extracorporeal liver surgery
        "WOS:000577961400012",  # Zawistowski M (2020) Outcomes of ex vivo liver resection and autotransplantation: meta-analysis
        "WOS:000884804400014",  # Lu Q, Aini A, Dong JH (2022) From liver surgery to liver transplant surgery: autotransplantation
        "WOS:000572859000001",  # Baimas-George M (2021) Vena cava reconstructive techniques with major liver resection
        "WOS:001248212000074",  # Li TE (2024) Hepatic echinococcosis bibliometric analysis
        "WOS:000226300800010",  # Schipper HG (2004) Diagnosis and treatment of hepatic echinococcosis: An overview
        "WOS:000177499500013",  # Khuroo MS (2002) Hydatid disease: Current status and recent advances
    }
    if not ae_pat.search(tiabde) and ut not in keep_landmark_uts:
        return (
            False,
            "Excluded_OffTopic_CE_or_Other",
            "Focused exclusively on Cystic Echinococcosis (E. granulosus), E. vogeli, or non-echinococcal conditions (matched only via WoS Keywords Plus)",
        )

    return True, "Included", "Core literature on surgical and clinical management of HAE"


def format_wos_record(data, ordered_tags):
    lines = []
    for tag in ordered_tags:
        vals = data.get(tag, [])
        if not vals:
            continue
        lines.append(f"{tag} {vals[0]}")
        for v in vals[1:]:
            lines.append(f"   {v}")
    lines.append("ER")
    return "\n".join(lines)


def main():
    raw_records = parse_wos_records(RAW_PATH)
    print(f"Loaded {len(raw_records)} raw records from {RAW_PATH}")

    strict_records_out = []
    full453_records_out = []
    exclusion_log = []
    parsed_strict = []
    parsed_full453 = []

    for idx, rec_text in enumerate(raw_records, 1):
        data, ordered_tags = parse_fields(rec_text)
        ut = data["UT"][0].strip() if data["UT"] else f"REC_{idx}"
        py = data["PY"][0].strip() if data["PY"] else ""
        ti_raw = " ".join(data["TI"]).strip()

        # Fix anonymous Ulm University cohort paper (WOS:001605718300001)
        if ut == "WOS:001605718300001":
            if "C1" not in data:
                data["C1"] = ["Ulm Univ Hosp, Dept Internal Med 3, Div Infect Dis, Ulm, Germany."]
                ordered_tags.insert(ordered_tags.index("AB") + 1, "C1")
            if "C3" not in data:
                data["C3"] = ["Ulm University"]
                ordered_tags.insert(ordered_tags.index("C1") + 1, "C3")

        # Clean HTML tags in TI and AB
        if "TI" in data:
            data["TI"] = [clean_html_entities(x) for x in data["TI"]]
        if "AB" in data:
            data["AB"] = [clean_html_entities(x) for x in data["AB"]]

        # Standardize Authors (AF and AU)
        if "AF" in data:
            std_afs = [standardize_author_af(x) for x in data["AF"]]
            if "AU" in data and len(data["AU"]) == len(std_afs):
                std_aus = [standardize_author_au(au, af) for au, af in zip(data["AU"], std_afs)]
            else:
                std_aus = [standardize_author_au(au) for au in data.get("AU", [])]
            data["AF"] = std_afs
            if "AU" in data:
                data["AU"] = std_aus

        # Standardize Author Keywords (DE) and Keywords Plus (ID)
        if "DE" in data:
            std_de = standardize_keywords(data["DE"])
            data["DE"] = [std_de] if std_de else []
        if "ID" in data:
            std_id = standardize_keywords(data["ID"])
            data["ID"] = [std_id.upper()] if std_id else []

        # Standardize C1 countries & institutions
        if "C1" in data:
            new_c1 = []
            for c1_line in data["C1"]:
                c1_line = re.sub(r"Peoples R China", "China", c1_line)
                c1_line = re.sub(r"\bTurkiye\b", "Turkey", c1_line)
                c1_line = re.sub(r"\b(England|Scotland|Wales|North Ireland)\b", "United Kingdom", c1_line)
                new_c1.append(c1_line)
            data["C1"] = new_c1

        keep_strict, category, reason = classify_record_for_prisma(data)

        if category == "Excluded_Retracted":
            exclusion_log.append({
                "UT": ut,
                "Year": py,
                "Authors": "; ".join(data.get("AF", [])[:3]),
                "Title": clean_html_entities(ti_raw),
                "Journal": " ".join(data.get("SO", [])),
                "Status": "Excluded (Retracted)",
                "Reason": reason,
            })
            continue

        # Add to full453 dataset (all non-retracted records)
        rec_formatted = format_wos_record(data, ordered_tags)
        full453_records_out.append(rec_formatted)
        parsed_full453.append(data)

        if keep_strict:
            strict_records_out.append(rec_formatted)
            parsed_strict.append(data)
        else:
            exclusion_log.append({
                "UT": ut,
                "Year": py,
                "Authors": "; ".join(data.get("AF", [])[:3]),
                "Title": clean_html_entities(ti_raw),
                "Journal": " ".join(data.get("SO", [])),
                "Status": category,
                "Reason": reason,
            })

    # Write cleaned WoS files
    strict_file = os.path.join(OUT_DIR, "data_cleaned", "wos_hae_surgery_strict_cleaned.txt")
    with open(strict_file, "w", encoding="utf-8") as f:
        f.write("FN Clarivate Analytics Web of Science\nVR 1.0\n")
        f.write("\n\n".join(strict_records_out))
        f.write("\n\nEF\n")

    full453_file = os.path.join(OUT_DIR, "data_cleaned", "wos_hae_surgery_full453_cleaned.txt")
    with open(full453_file, "w", encoding="utf-8") as f:
        f.write("FN Clarivate Analytics Web of Science\nVR 1.0\n")
        f.write("\n\n".join(full453_records_out))
        f.write("\n\nEF\n")

    # Write PRISMA exclusion log CSV
    csv_file = os.path.join(OUT_DIR, "tables", "prisma_exclusion_log.csv")
    with open(csv_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["UT", "Year", "Authors", "Title", "Journal", "Status", "Reason"])
        writer.writeheader()
        writer.writerows(exclusion_log)

    # Write VOSviewer Thesaurus files (tab-separated: label \t replace by)
    def write_thesaurus(filename, mapping):
        path = os.path.join(OUT_DIR, "thesaurus", filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write("label\treplace by\n")
            for k, v in sorted(mapping.items()):
                if k.lower() != v.lower() or k != v:
                    f.write(f"{k}\t{v}\n")

    write_thesaurus("thesaurus_authors.txt", AUTHOR_AF_MAP)
    write_thesaurus("thesaurus_keywords.txt", KEYWORD_MAP)
    write_thesaurus("thesaurus_organizations.txt", INSTITUTION_MAP)
    write_thesaurus("thesaurus_countries.txt", COUNTRY_MAP)

    print(f"Strict PRISMA dataset: {len(parsed_strict)} records -> {strict_file}")
    print(f"Full non-retracted dataset: {len(parsed_full453)} records -> {full453_file}")
    print(f"Excluded records logged: {len(exclusion_log)} -> {csv_file}")
    status_counts = Counter(x["Status"] for x in exclusion_log)
    for k, v in status_counts.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
