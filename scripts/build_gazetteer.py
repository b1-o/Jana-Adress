#!/usr/bin/env python3
"""
Сборка справочника -> data/gazetteer.sqlite

Источники (все кладутся в репозиторий, интернет при разборе не нужен):
  data/kato.json            — КАТО НК РК 11-2025 (ред. 18.09.2026): области, города,
                              районы, сёла/посёлки (RU + KZ);
  data/city_districts.json  — районы в городах респ. значения (КАТО ред. 18.12.2024:
                              в свежей редакции их нет);
  data/osm/<город>.json     — улицы и жилые массивы/микрорайоны из OSM (Overpass);
  data/manual/*.json        — ручные уточнения команды (алиасы, привязка мкр -> район).

Запуск:
    python scripts/build_kato.py            # КАТО 2026 -> data/kato.json
    python scripts/build_city_districts.py  # КАТО 2024 -> data/city_districts.json
    python scripts/fetch_osm.py             # OSM -> data/osm/*.json (нужна сеть)
    python scripts/build_gazetteer.py       # всё вместе -> data/gazetteer.sqlite
"""
from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.textnorm import norm_key  # noqa: E402
from app.parser import STREET_TYPES  # noqa: E402

# русские канонические названия областей (в КАТО они то «область Абай», то «Акмолинская область»)
PROVINCE_CANON = {
    "Абай": "Абайская область",
    "Акмолинская": "Акмолинская область",
    "Актюбинская": "Актюбинская область",
    "Алматинская": "Алматинская область",
    "Атырауская": "Атырауская область",
    "Западно-Казахстанская": "Западно-Казахстанская область",
    "Жамбылская": "Жамбылская область",
    "Жетісу": "область Жетісу",
    "Карагандинская": "Карагандинская область",
    "Костанайская": "Костанайская область",
    "Кызылординская": "Кызылординская область",
    "Мангистауская": "Мангистауская область",
    "Павлодарская": "Павлодарская область",
    "Северо-Казахстанская": "Северо-Казахстанская область",
    "Туркестанская": "Туркестанская область",
    "Ұлытау": "область Ұлытау",
    "Восточно-Казахстанская": "Восточно-Казахстанская область",
    # города республиканского значения — сами себе «область»
    "Астана": "Астана",
    "Алматы": "Алматы",
    "Шымкент": "Шымкент",
}

TYPE_PREFIXES = [(t, variants) for t, variants in STREET_TYPES]


from collections import Counter


class DistrictIndex:
    """Районы городов по полигонам (data/districts/*.json) -> привязка улиц и жилмассивов.

    Без этого поля district не восстановить: в КАТО текущей редакции районов в городах нет,
    а OSM их геометрию удалил. Источник полигонов и его статус описаны в README.
    """

    def __init__(self, pattern: str = "data/districts/*.json"):
        self.by_city: dict[str, list] = {}
        self.loaded: dict[str, int] = {}
        try:
            from shapely.geometry import MultiPolygon, Polygon
        except ImportError:
            print("[warn] нет shapely — район не будет восстановлен (pip install shapely)")
            return
        for path in sorted(glob.glob(pattern)):
            city = os.path.basename(path)[:-5]
            data = json.load(open(path, encoding="utf-8"))
            polys = []
            for d in data.get("districts", []):
                rings = [Polygon(r) for r in d.get("rings", []) if len(r) >= 4]
                if not rings:
                    continue
                geom = MultiPolygon(rings)
                if not geom.is_valid:
                    geom = geom.buffer(0)
                if geom.is_empty:
                    continue
                polys.append((d["name"], geom))
            self.by_city[city] = polys
            self.loaded[city] = len(polys)
        if self.loaded:
            print("[districts] полигоны:", ", ".join(f"{c}: {n}" for c, n in self.loaded.items()))

    def lookup(self, city: str, lat: float | None, lon: float | None) -> str | None:
        if lat is None or lon is None or city not in self.by_city:
            return None
        from shapely.geometry import Point
        p = Point(lon, lat)
        for name, geom in self.by_city[city]:
            if geom.contains(p):
                return name
        return None


def split_type(name: str) -> tuple[str | None, str]:
    """'проспект Абая' -> ('проспект', 'Абая');  'Улица Наурызбай Батыра' -> ('улица', 'Наурызбай Батыра')."""
    n = name.strip()
    for canonical, variants in TYPE_PREFIXES:
        for v in sorted(variants, key=len, reverse=True):
            m = re.match(rf"^{re.escape(v)}\s*\.?\s+", n, re.IGNORECASE)
            if m:
                return canonical, n[m.end():].strip()
    return None, n


def province_of(name_ru: str) -> str | None:
    base = name_ru.replace("область", "").strip()
    for key, canon in PROVINCE_CANON.items():
        if key.lower() in base.lower() or base.lower() in key.lower():
            return canon
    return None


def main() -> None:
    db_path = "data/gazetteer.sqlite"
    if os.path.exists(db_path):
        os.remove(db_path)
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.executescript("""
    CREATE TABLE provinces (code TEXT, name TEXT, name_kk TEXT, key TEXT, source TEXT);
    CREATE TABLE cities    (code TEXT, name TEXT, name_kk TEXT, province TEXT, key TEXT,
                            kind TEXT, is_city_of_republic INTEGER, source TEXT, rank INTEGER);
    CREATE TABLE city_districts (code TEXT, name TEXT, name_kk TEXT, city TEXT, key TEXT, source TEXT);
    CREATE TABLE districts (code TEXT, name TEXT, name_kk TEXT, kind TEXT, city TEXT,
                            province TEXT, key TEXT, source TEXT);
    CREATE TABLE settlements (code TEXT, name TEXT, name_kk TEXT, province TEXT, key TEXT,
                              kind TEXT, source TEXT);
    CREATE TABLE streets   (key TEXT, name TEXT, street_type TEXT, city TEXT, district TEXT,
                             cnt INTEGER, source TEXT);
    CREATE TABLE living_areas (key TEXT, name TEXT, city TEXT, district TEXT, kind TEXT,
                               cnt INTEGER, source TEXT, rank INTEGER);
    CREATE INDEX ix_prov_key ON provinces(key);
    CREATE INDEX ix_city_key ON cities(key);
    CREATE INDEX ix_dist_key ON districts(key);
    CREATE INDEX ix_set_key ON settlements(key);
    CREATE INDEX ix_street_key ON streets(key);
    CREATE INDEX ix_la_key ON living_areas(key);
    """)

    stats: dict[str, int] = {}

    # ---------------------------------------------------------------- КАТО
    kato = json.load(open("data/kato.json", encoding="utf-8"))
    province_by_code: dict[str, str] = {}

    for it in kato:
        if it["kind"] != "region":
            continue
        canon = province_of(it["name_ru"]) or it["name_ru"]
        province_by_code[it["code"]] = canon
        keys = {norm_key(it["name_ru"]), norm_key(it["name_kk"]), norm_key(canon)}
        base = it["name_ru"].replace("область", "").strip()
        keys |= {norm_key(base), norm_key(base + " облысы"), norm_key(base + "ская область")}
        for k in filter(None, keys):
            cur.execute("INSERT INTO provinces VALUES (?,?,?,?,?)",
                        (it["code"], canon, it["name_kk"], k, "КАТО НК РК 11-2025"))

    # города республиканского значения = отдельные «области»
    for city, code in (("Астана", "710000000"), ("Алматы", "750000000"), ("Шымкент", "790000000")):
        for k in (norm_key(city), norm_key(city + " қаласы"), norm_key(city + " город")):
            cur.execute("INSERT INTO provinces VALUES (?,?,?,?,?)",
                        (code, city, city, k, "КАТО НК РК 11-2025 (город респ. значения)"))

    def province_for(code: str) -> str | None:
        return province_by_code.get(code[:2] + "0" * 7)

    for it in kato:
        parent_prov = province_for(it["code"])
        if it["kind"] in ("city", "city_admin"):
            name = it["name_ru"]
            prov = parent_prov or name
            is_rep = name in ("Астана", "Алматы", "Шымкент")
            if is_rep:
                prov = name
            keys = {norm_key(name), norm_key(it["name_kk"]), norm_key(name + " город")}
            if name == "Алматы":
                keys |= {norm_key("алма-ата"), norm_key("алма ата")}
            for k in filter(None, keys):
                cur.execute("INSERT INTO cities VALUES (?,?,?,?,?,?,?,?,?)",
                            (it["code"], name, it["name_kk"], prov, k, "city",
                             int(is_rep), "КАТО НК РК 11-2025", 0))
        elif it["kind"] == "district":
            keys = {norm_key(it["name_ru"]), norm_key(it["name_kk"])}
            # район в городе респ. значения: код 75xxxxxxx -> «Алматы» (сам себе область)
            rep_city = {"71": "Астана", "75": "Алматы", "79": "Шымкент"}.get(it["code"][:2])
            in_city = rep_city if rep_city and it["code"][2:4] != "00" else None
            for k in filter(None, keys):
                cur.execute("INSERT INTO districts VALUES (?,?,?,?,?,?,?,?)",
                            (it["code"], it["name_ru"], it["name_kk"],
                             "city_district" if in_city else "district",
                             in_city, in_city or parent_prov, k, "КАТО НК РК 11-2025"))
                if in_city:
                    cur.execute("INSERT INTO city_districts VALUES (?,?,?,?,?,?)",
                                (it["code"], it["name_ru"], it["name_kk"], in_city, k,
                                 "КАТО НК РК 11-2025"))
        elif it["kind"] in ("village", "settlement", "other") and it["name_ru"]:
            keys = {norm_key(it["name_ru"]), norm_key(it["name_kk"])}
            for k in filter(None, keys):
                cur.execute("INSERT INTO settlements VALUES (?,?,?,?,?,?,?)",
                            (it["code"], it["name_ru"], it["name_kk"], parent_prov, k,
                             it["kind"], "КАТО НК РК 11-2025"))
                # посёлки/сёла тоже могут быть «городом» в адресной строке (Боралдай, Пришахтинск)
                cur.execute("INSERT INTO cities VALUES (?,?,?,?,?,?,?,?,?)",
                            (it["code"], it["name_ru"], it["name_kk"], parent_prov, k,
                             "settlement", 0, "КАТО НК РК 11-2025", 1))
    # у населённых пунктов ищем город-родителя по иерархии кодов КАТО:
    # «Пришахтинск» -> «Караганда» (это нужно, чтобы восстановить city по жилмассиву)
    def parent_city(code: str) -> str | None:
        cur_code = code
        for _ in range(4):
            cur_code = cur_code[:6] + "0" * 3 if cur_code[6:] != "000" else cur_code[:4] + "0" * 5
            row = next((x for x in kato if x["code"] == cur_code), None)
            if row and row["kind"] == "city":
                return row["name_ru"]
        return None

    for it in kato:
        if it["kind"] in ("settlement", "village") and it["name_ru"]:
            city_hint = parent_city(it["code"])
            for k in {norm_key(it["name_ru"]), norm_key(it["name_kk"])}:
                if not k:
                    continue
                cur.execute("INSERT INTO living_areas VALUES (?,?,?,?,?,?,?,?)",
                            (k, it["name_ru"], city_hint, None, it["kind"], 1,
                             "КАТО НК РК 11-2025", 2))
                if city_hint:
                    cur.execute("UPDATE cities SET province=COALESCE(province, ?) WHERE key=?", (city_hint, k))
    stats["КАТО"] = len(kato)

    # ------------------------------------------------- районы в городах (КАТО 2024)
    n_city_districts = 0
    if os.path.exists("data/city_districts.json"):
        for d in json.load(open("data/city_districts.json", encoding="utf-8")):
            keys = {norm_key(d["name_ru"]), norm_key(d["name_kk"]),
                    norm_key(d["ru_full"]), norm_key(d["kk_full"])}
            for k in filter(None, keys):
                cur.execute("INSERT INTO districts VALUES (?,?,?,?,?,?,?,?)",
                            (d["code"], d["name_ru"], d["name_kk"], "city_district",
                             d["city"], d["city"], k, d["source"]))
                cur.execute("INSERT INTO city_districts VALUES (?,?,?,?,?,?)",
                            (d["code"], d["name_ru"], d["name_kk"], d["city"], k, d["source"]))
            n_city_districts += 1
    stats["районы в городах"] = n_city_districts

    # ------------------------------------------------------------- OSM
    n_streets = n_places = 0
    n_with_district = 0
    didx = DistrictIndex()
    for path in sorted(glob.glob("data/osm/*.json")):
        if os.path.basename(path).startswith("_"):
            continue
        city = os.path.basename(path)[:-5]
        data = json.load(open(path, encoding="utf-8"))
        street_bucket: dict[str, dict] = {}
        for st in data.get("streets", []):
            street_district = st.get("district") or didx.lookup(city, st.get("lat"), st.get("lon"))
            # длинная улица пересекает несколько районов: копим «голоса» сегментов
            votes: Counter = Counter()
            for variant in {st.get("name") or "", st.get("name_ru") or "", st.get("name_kk") or ""}:
                if not variant:
                    continue
                stype, base = split_type(variant)
                stype2, base2 = split_type(st.get("name_ru") or st.get("name") or variant)
                for key_name in {base, base2}:
                    if not key_name:
                        continue
                    key = norm_key(key_name)
                    if not key or key.isdigit():
                        continue
                    bucket = street_bucket.setdefault(key, {
                        "key": key, "name": key_name, "street_type": stype2 or stype,
                        "city": city, "district": street_district, "cnt": 0,
                        "source": "OpenStreetMap (Overpass)"
                                  + (" + районы OSM" if street_district else ""),
                    })
                    bucket["cnt"] += 1
                    if street_district:
                        bucket.setdefault("votes", Counter())[street_district] += 1
                    if bucket["street_type"] is None:
                        bucket["street_type"] = stype2 or stype
        for b in street_bucket.values():
            votes = b.pop("votes", None)
            if votes:
                # район = самый частый среди сегментов улицы (взвешенно по их количеству)
                b["district"] = votes.most_common(1)[0][0]
            cur.execute("INSERT INTO streets VALUES (?,?,?,?,?,?,?)",
                        (b["key"], b["name"], b["street_type"], b["city"], b["district"],
                         b["cnt"], b["source"]))
        n_streets += len(street_bucket)
        n_with_district += sum(1 for b in street_bucket.values() if b["district"])

        la_bucket: dict[str, dict] = {}
        for pl in data.get("places", []):
            pl["district"] = pl.get("district") or didx.lookup(city, pl.get("lat"), pl.get("lon"))
            for variant, kind in ((pl.get("name_ru") or pl.get("name"), pl.get("place")),
                                  (pl.get("name_kk"), pl.get("place")),
                                  (pl.get("name"), pl.get("place"))):
                if not variant:
                    continue
                stype, base = split_type(variant)
                key = norm_key(base)
                if not key:
                    continue
                b = la_bucket.setdefault(key, {"key": key, "name": base, "city": city,
                                               "district": pl.get("district"), "kind": kind, "cnt": 0})
                b["cnt"] += 1
                if pl.get("district"):
                    b.setdefault("votes", Counter())[pl["district"]] += 1
        for b in la_bucket.values():
            votes = b.pop("votes", None)
            if votes:
                b["district"] = votes.most_common(1)[0][0]
            cur.execute("INSERT INTO living_areas VALUES (?,?,?,?,?,?,?,?)",
                        (b["key"], b["name"], b["city"], b["district"], b["kind"], b["cnt"],
                         "OpenStreetMap (Overpass)", 1))
        n_places += len(la_bucket)
        with_d = sum(1 for b in la_bucket.values() if b["district"]) + \
                 sum(1 for b in street_bucket.values() if b["district"])
        print(f"[osm] {city}: улиц-ключей {len(street_bucket)}, жилмассивов {len(la_bucket)}, "
              f"с районом {with_d}")
    stats["улицы (OSM)"] = n_streets
    stats["жилые массивы (OSM)"] = n_places
    stats["улицы/мкр с районом"] = n_with_district

    # ------------------------------------------------------------ ручные данные
    for path in sorted(glob.glob("data/manual/*.json")):
        data = json.load(open(path, encoding="utf-8"))
        name = os.path.basename(path)
        added = 0
        for item in data if isinstance(data, list) else []:
            if item.get("kind") == "living_area":
                for v in item.get("aliases", []) + [item["name"]]:
                    cur.execute("INSERT INTO living_areas VALUES (?,?,?,?,?,?,?,?)",
                                (norm_key(v), item["name"], item.get("city"), item.get("district"),
                                 "manual", 100, f"manual/{name}", 0))
                    added += 1
            elif item.get("kind") == "street":
                for v in item.get("aliases", []) + [item["name"]]:
                    cur.execute("INSERT INTO streets VALUES (?,?,?,?,?,?,?)",
                                (norm_key(v), item["name"], item.get("street_type"), item.get("city"),
                                 item.get("district"), 100, f"manual/{name}"))
                    added += 1
            elif item.get("kind") == "district":
                for v in item.get("aliases", []) + [item["name"]]:
                    cur.execute("INSERT INTO districts VALUES (?,?,?,?,?,?,?,?)",
                                (item.get("code"), item["name"], item.get("name_kk"), item.get("dkind", "manual"),
                                 item.get("city"), item.get("province"), norm_key(v), f"manual/{name}"))
                    added += 1
        if added:
            print(f"[manual] {name}: +{added}")

    con.commit()

    print("\n=== ИТОГО справочник data/gazetteer.sqlite ===")
    for table in ("provinces", "cities", "districts", "city_districts", "settlements",
                  "streets", "living_areas"):
        n = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        stats[table] = n
        print(f"  {table:14s}: {n}")
    print(f"  размер файла   : {os.path.getsize(db_path) / 1e6:.1f} МБ")
    json.dump(stats, open("data/gazetteer_stats.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    con.close()


if __name__ == "__main__":
    main()
