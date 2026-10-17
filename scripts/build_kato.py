#!/usr/bin/env python3
"""
КАТО (НК РК 11-2025, актуализация 18.09.2026) -> data/kato.json

Источник: Бюро национальной статистики РК
https://stat.gov.kz/ru/classifiers/statistical/21/  (файл «КАТО_<дата>.xlsx»)

Запуск: python scripts/build_kato.py [путь_к_xlsx]
Если файла нет, скрипт скачает актуальный (нужен интернет).
"""
from __future__ import annotations

import json
import os
import re
import sys

STAT_URL_PAGE = "https://stat.gov.kz/ru/classifiers/statistical/21/"
FALLBACK_XLSX = ("https://stat.gov.kz/upload/iblock/a7d/"
                 "eqogm92xc0udumlzfzffhcrutk0fjhb4/КАТО_18.09.2026.xlsx")


def download(url: str, dest: str) -> None:
    import urllib.parse
    import urllib.request
    req = urllib.request.Request(urllib.parse.quote(url, safe=":/?=&%"), headers={"User-Agent": "Mozilla/5.0"})
    print(f"[net] {url}")
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        f.write(r.read())


def classify(name_ru: str, name_kk: str, code: str) -> str:
    n_ru, n_kk = name_ru.lower(), name_kk.lower()
    if "облыс" in n_kk or n_ru.startswith("область") or "область" in n_ru:
        return "region"
    if "қ.Ә.".lower() in n_kk.lower() or "г.а." in n_ru.lower():
        return "city_admin"
    if "ауданы" in n_kk or "район" in n_ru:
        return "district"
    if "с.о." in n_ru or "а.о." in n_ru or "п.о." in n_ru or "а.о" in n_kk or "с.о" in n_kk:
        return "rural_okrug"
    if n_ru.startswith("г.") or n_kk.startswith("қ."):
        return "city"
    if n_ru.startswith("с.") or n_ru.startswith("а.") or n_kk.startswith("а."):
        return "village"
    if n_ru.startswith("п.") or "кент" in n_kk or "кент" in n_ru:
        return "settlement"
    return "other"


PREFIX_RE = re.compile(
    r"^\s*(г\.|қ\.|с\.|а\.|п\.|кент|ст-ца|ст\.|ауыл|село|пос\.|разъезд|рзд\.)\s*", re.IGNORECASE)


def clean_name(name: str) -> str:
    if not name:
        return ""
    n = name.strip()
    n = re.sub(r"\s*(Г\.А\.|Қ\.Ә\.)$", "", n).strip()
    n = re.sub(r"\s*(с\.о\.|а\.о\.|п\.о\.)$", "", n, flags=re.IGNORECASE).strip()
    n = re.sub(r"\s*(ауданы|район(а)?)$", "", n, flags=re.IGNORECASE).strip()
    n = PREFIX_RE.sub("", n).strip()
    return n


def main() -> None:
    src = sys.argv[1] if len(sys.argv) > 1 else "/tmp/kato.xlsx"
    if not os.path.exists(src) or os.path.getsize(src) < 100_000:
        os.makedirs("/tmp", exist_ok=True)
        download(FALLBACK_XLSX, "/tmp/kato.xlsx")
        src = "/tmp/kato.xlsx"

    import openpyxl

    wb = openpyxl.load_workbook(src, read_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    idx = {str(h).strip(): i for i, h in enumerate(header) if h is not None}
    i_code, i_ru, i_kk = idx.get("te", 0), idx.get("rus_name", 7), idx.get("kaz_name", 6)

    items = []
    for r in rows[1:]:
        code = str(r[i_code]).zfill(9)
        ru = (r[i_ru] or "").strip()
        kk = (r[i_kk] or "").strip()
        if not ru and not kk:
            continue
        kind = classify(ru, kk, code)
        items.append({
            "code": code,
            "kind": kind,
            "ru": ru,
            "kk": kk,
            "name_ru": clean_name(ru),
            "name_kk": clean_name(kk),
            "parent": code[:2] + "0" * 7 if code[2:4] != "00" else None,
        })

    # иерархия: заполняем для «детей» id родителя по коду
    by_code = {i["code"]: i for i in items}
    for it in items:
        c = it["code"]
        for cut in (2, 4, 6):
            cand = c[:cut] + "0" * (9 - cut)
            if cand != c and cand in by_code:
                it["parent"] = cand
                break

    out = "data/kato.json"
    os.makedirs("data", exist_ok=True)
    json.dump(items, open(out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    from collections import Counter
    print(f"[ok] {len(items)} записей -> {out}")
    print("    по видам:", dict(Counter(i["kind"] for i in items)))


if __name__ == "__main__":
    main()
