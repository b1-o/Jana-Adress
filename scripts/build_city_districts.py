#!/usr/bin/env python3
"""
Районы в городах республиканского значения -> data/city_districts.json

Зачем отдельный источник: в действующей редакции КАТО НК РК 11-2025
(актуализация 18.09.2026, файл «КАТО_18.09.2026.xlsx») районы в городах
**не публикуются** — там только «г.Алматы», «г.Астана», «г.Шымкент».
А в редакции «КАТО_18.12.2024.xls» они есть (19 записей).

Именно поэтому поле district нельзя заполнить только по свежему КАТО —
нужен дополнительный источник. Скрипт берёт его из архива классификаторов:
https://stat.gov.kz/ru/classifiers/archive/

Запуск: python scripts/build_city_districts.py [путь_к_КАТО_18.12.2024.xls]
"""
from __future__ import annotations

import json
import os
import sys

ARCHIVE_URL = ("https://stat.gov.kz/upload/iblock/fc3/bkmzatfyk7e7919jn7gyqs5q91hyb78n/"
               "КАТО_18.12.2024.xls")

# город республиканского значения -> префикс КАТО
CITY_PREFIX = {"Алматы": "75", "Астана": "71", "Шымкент": "79"}


def download(dest: str) -> str:
    import urllib.parse
    import urllib.request
    print(f"[net] {ARCHIVE_URL}")
    req = urllib.request.Request(urllib.parse.quote(ARCHIVE_URL, safe=":/?=&%"),
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
        f.write(r.read())
    return dest


def main() -> None:
    src = sys.argv[1] if len(sys.argv) > 1 else "data/source/КАТО_18.12.2024.xls"
    if not os.path.exists(src):
        os.makedirs(os.path.dirname(src) or ".", exist_ok=True)
        src = download(src)

    import pandas as pd

    df = pd.read_excel(src, header=None, dtype=str).fillna("")
    df.columns = ["te", "ab", "cd", "ef", "hij", "k", "kaz_name", "rus_name", "nn"][: len(df.columns)]

    out = []
    for city, prefix in CITY_PREFIX.items():
        mask = df["te"].str.startswith(prefix) & df["rus_name"].str.contains("район", case=False, na=False)
        for _, row in df[mask].iterrows():
            code, ru, kk = row["te"], row["rus_name"].strip(), row["kaz_name"].strip()
            # «район Алматы» / «Ауэзовский район» -> базовое имя без слова «район»
            name_ru = ru.replace("район", "").replace("Район", "").strip()
            name_kk = kk.replace("ауданы", "").strip()
            out.append({
                "code": code,
                "city": city,
                "name_ru": name_ru,
                "name_kk": name_kk,
                "ru_full": ru,
                "kk_full": kk,
                "source": "КАТО НК РК 11-2009 (ред. 18.12.2024), stat.gov.kz",
            })

    os.makedirs("data", exist_ok=True)
    json.dump(out, open("data/city_districts.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"[ok] {len(out)} районов в городах -> data/city_districts.json")
    for o in out:
        print(f"   {o['code']} {o['city']:8s} {o['name_ru']}")


if __name__ == "__main__":
    main()
