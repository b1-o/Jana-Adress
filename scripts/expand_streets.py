#!/usr/bin/env python3
"""Догрузка улиц в справочник из OpenStreetMap.

Проблема, которую решает скрипт: в исходной сборке улицы были только по 5 городам
(Алматы, Астана, Шымкент, Актобе, Караганда), поэтому адрес из любого другого
города разбирался без проверки улицы по справочнику.

Что делает:
  * берёт список городов и для каждого спрашивает Overpass API улицы с именем;
  * определяет тип улицы по окончанию названия (даңғылы -> проспект, көшесі -> улица);
  * раскладывает в таблицу streets: ключ в русской графике + вариант без типа;
  * пишет прогресс в data/osm/_streets_progress.json — можно прервать и продолжить.

Запуск:
    python scripts/expand_streets.py                 # все города из списка
    python scripts/expand_streets.py --cities Тараз,Семей
    python scripts/expand_streets.py --limit 5       # только первые 5
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.textnorm import norm_key  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "gazetteer.sqlite"
PROGRESS = ROOT / "data" / "osm" / "_streets_progress.json"

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
UA = "jana-address-hackathon/1.0 (gazetteer builder)"

#: крупные города Казахстана (по убыванию населения) — те, где чаще всего адреса
CITIES = [
    "Тараз", "Павлодар", "Усть-Каменогорск", "Семей", "Атырау", "Актау",
    "Костанай", "Кызылорда", "Уральск", "Петропавловск", "Туркестан",
    "Талдыкорган", "Темиртау", "Кокшетау", "Экибастуз", "Рудный", "Жезказган",
    "Балхаш", "Кентау", "Сатпаев", "Конаев", "Каскелен", "Талгар", "Есик",
    "Арысь", "Щучинск", "Степногорск", "Шахтинск", "Лисаковск", "Аксу",
    "Риддер", "Жанаозен", "Сарканд", "Ушарал", "Зайсан", "Аягоз",
    "Жаркент", "Шу", "Каратау", "Житикара", "Атбасар", "Есиль",
    "Акколь", "Степняк", "Макинск", "Аркалык", "Текели", "Уштобе",
    "Ленгер", "Сарыагаш", "Жетысай", "Шардара", "Казалинск", "Аральск",
    "Форт-Шевченко", "Шалкар", "Эмба", "Хромтау", "Кандыагаш", "Темир",
    "Байконыр", "Алга", "Аксай", "Кульсары", "Жем", "Каражал",
    "Приозерск", "Курчатов", "Серебрянск", "Шемонаиха", "Булаево",
    "Сергеевка", "Мамлютка", "Тайынша", "Косшы", "Алатау", "Алтай",
]

#: окончание названия -> канонический тип
SUFFIXES = [
    ("даңғылы", "проспект"), ("даңғыл", "проспект"), ("данғылы", "проспект"),
    ("данғыл", "проспект"), ("проспект", "проспект"), ("проспектісі", "проспект"),
    ("көшесі", "улица"), ("кошеси", "улица"), ("көше", "улица"), ("улица", "улица"),
    ("шағын ауданы", "микрорайон"), ("шағын аудан", "микрорайон"),
    ("ықшамаудан", "микрорайон"), ("микрорайон", "микрорайон"), ("мкр", "микрорайон"),
    ("тас жолы", "шоссе"), ("тас жол", "шоссе"), ("шоссе", "шоссе"),
    ("бульвары", "бульвар"), ("бульвар", "бульвар"),
    ("алаңы", "площадь"), ("алаң", "площадь"), ("площадь", "площадь"),
    ("тұйық", "тупик"), ("туйык", "тупик"), ("переулок", "переулок"), ("тупик", "тупик"),
    ("квартал", "квартал"), ("тоқсан", "квартал"), ("проезд", "проезд"),
    ("аллея", "аллея"), ("набережная", "набережная"), ("станция", "станция"),
    # русские сокращения, как их пишут в OSM: «Абая ул.»
    ("ул.", "улица"), ("ул", "улица"), ("пр-т", "проспект"), ("пр.", "проспект"),
    ("пер.", "переулок"), ("б-р", "бульвар"), ("пл.", "площадь"), ("наб.", "набережная"),
    ("ш.", "шоссе"), ("туп.", "тупик"), ("мкр.", "микрорайон"), ("кв-л", "квартал"),
]


def http_json(query: str, tries: int = 5) -> dict:
    last: Exception | None = None
    for i in range(tries):
        for ep in ENDPOINTS:
            try:
                data = urllib.parse.urlencode({"data": query}).encode()
                req = urllib.request.Request(ep, data=data, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=150) as r:
                    return json.load(r)
            except Exception as e:  # noqa: BLE001
                last = e
        time.sleep(4 * (i + 1))
    raise RuntimeError(f"overpass failed: {last}")


def city_bbox(city: str) -> list[float] | None:
    """Границы города через Nominatim (area-запросы Overpass находят не все города)."""
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": f"{city}, Казахстан", "format": "json", "limit": 1})
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                js = json.load(r)
            if not js:
                return None
            s_, n_, w_, e_ = (float(x) for x in js[0]["boundingbox"])
            return [s_, w_, n_, e_]
        except Exception:  # noqa: BLE001
            time.sleep(3 * (attempt + 1))
    return None


def query_city(city: str) -> list[str]:
    bbox = city_bbox(city)
    if not bbox:
        return []
    s_, w_, n_, e_ = bbox
    q = f"""[out:json][timeout:150];
way({s_},{w_},{n_},{e_})["highway"]["name"];
out tags;"""
    js = http_json(q)
    names: list[str] = []
    for el in js.get("elements", []):
        nm = (el.get("tags") or {}).get("name")
        if nm:
            names.append(nm.strip())
    return names


def split_name(name: str) -> tuple[str, str | None]:
    """'Алаш даңғылы' -> ('Алаш', 'проспект'); 'улица Абая' -> ('Абая', 'улица').

    В OSM тип стоит то после названия («Абай көшесі»), то перед ним
    («улица Абая») — учитываем оба порядка.
    """
    low = name.lower().strip()
    for suf, typ in SUFFIXES:
        if low.endswith(" " + suf) or low == suf:
            base = name[: len(name) - len(suf)].strip(" ,.")
            return (base or name), typ
    for pre, typ in SUFFIXES:
        if low.startswith(pre + " "):
            base = name[len(pre):].strip(" ,.")
            return (base or name), typ
    return name, None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cities", default="")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    targets = [c.strip() for c in args.cities.split(",") if c.strip()] or CITIES
    if args.limit:
        targets = targets[: args.limit]

    progress: dict[str, int] = {}
    if PROGRESS.exists():
        progress = json.loads(PROGRESS.read_text(encoding="utf-8"))

    conn = sqlite3.connect(DB)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_streets_key_city ON streets(key, city)"
    )
    done_cities = {r[0] for r in conn.execute(
        "SELECT DISTINCT city FROM streets WHERE city IS NOT NULL")}
    print(f"уже есть улицы по {len(done_cities)} городам: {', '.join(sorted(done_cities))}")

    total = 0
    for i, city in enumerate(targets, 1):
        if city in progress and progress[city] > 0:
            print(f"[{i}/{len(targets)}] {city}: уже загружено ({progress[city]}) — пропуск")
            continue
        try:
            names = query_city(city)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(targets)}] {city}: ОШИБКА {e}")
            continue

        rows: dict[tuple[str, str], tuple] = {}
        for name in set(names):
            base, typ = split_name(name)
            key_full = norm_key(name)
            if not key_full:
                continue
            rows[(key_full, name)] = (key_full, name, typ, city, None, 1, "OpenStreetMap (Overpass)")
            if base != name:
                key_base = norm_key(base)
                if key_base:
                    rows[(key_base, base)] = (key_base, base, typ, city, None, 1, "OpenStreetMap (Overpass)")

        conn.execute("DELETE FROM streets WHERE city=?", (city,))
        conn.executemany(
            "INSERT INTO streets(key, name, street_type, city, district, cnt, source) "
            "VALUES (?,?,?,?,?,?,?)", list(rows.values()))
        conn.commit()

        progress[city] = len(rows)
        total += len(rows)
        PROGRESS.parent.mkdir(parents=True, exist_ok=True)
        PROGRESS.write_text(json.dumps(progress, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[{i}/{len(targets)}] {city}: +{len(rows)} записей (всего в базе +{total})")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_streets_key ON streets(key)")
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM streets").fetchone()[0]
    cities = conn.execute("SELECT COUNT(DISTINCT city) FROM streets WHERE city IS NOT NULL").fetchone()[0]
    conn.close()
    print(f"\nИтог: улиц {n}, городов {cities}")


if __name__ == "__main__":
    main()
