#!/usr/bin/env python3
"""
Границы районов городов республиканского значения (Алматы, Астана, Шымкент)
-> data/districts/<город>.json

Зачем: в КАТО текущей редакции районов в городах нет, а в OSM они лежат на
admin_level=6 (не 8, как обычно) — поэтому отдельный шаг сборки.

После этого шага build_gazetteer.py раскладывает улицы и жилмассивы по районам
(point-in-polygon), и поле district можно восстанавливать так же, как в примере
организаторов: «Мкр Аксай 3а» -> район «Ауэзовский».

Запуск (нужна сеть, это этап подготовки, а не работы решения):
    python scripts/fetch_districts.py
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.textnorm import norm_key  # noqa: E402

UA = {"User-Agent": "jana-address-hackathon/0.4 (district boundaries builder)"}
ENDPOINTS = ("https://overpass-api.de/api/interpreter",
             "https://overpass.kumi.systems/api/interpreter")

#: города респ. значения и их bbox (широта/долгота хранятся в data/osm/_cities.json)
REPUBLIC_CITIES = ("Алматы", "Астана", "Шымкент")


def overpass(query: str) -> dict:
    last = None
    for ep in ENDPOINTS:
        for attempt in range(3):
            try:
                data = urllib.parse.urlencode({"data": query}).encode()
                req = urllib.request.Request(ep, data=data, headers=UA)
                with urllib.request.urlopen(req, timeout=240) as r:
                    return json.load(r)
            except Exception as exc:  # noqa: BLE001
                last = exc
                print(f"    ! {ep.split('/')[2]}: {str(exc)[:70]}")
                time.sleep(4 * (attempt + 1))
    raise RuntimeError(f"overpass недоступен: {last}")


def name_patterns(names: list[str]) -> list[str]:
    """Из «Ауэзовский» / «Әуезов ауданы» сделать короткие шаблоны для regex: «Ауэзов», «Әуезов»."""
    import re as _re
    out = set()
    for n in names:
        if not n:
            continue
        stem = _re.sub(r"\s*(район[а-я]*|ауданы|область|облысы)\s*", " ", n, flags=_re.IGNORECASE).strip()
        stem = _re.sub(r"(ский|ская|ское|ий|ый|ой|ая|ое)$", "", stem, flags=_re.IGNORECASE).strip()
        if len(stem) >= 4:
            out.add(stem)
    return sorted(out)


def find_relations(city_names: list[str], bbox: tuple[float, float, float, float]) -> list[dict]:
    """Найти админ-отношения районов по именам (из КАТО) и оставить те, чей центр в bbox города."""
    import re as _re
    south, west, north, east = bbox
    pattern = "|".join(_re.escape(p) for p in name_patterns(city_names))
    if not pattern:
        return []
    q = f"""
[out:json][timeout:180];
relation["boundary"="administrative"]["admin_level"~"^(6|7|8)$"]["name"~"{pattern}",i];
out tags center;
"""
    found = []
    for rel in overpass(q).get("elements", []):
        tags = rel.get("tags", {})
        center = rel.get("center") or {}
        lat, lon = center.get("lat"), center.get("lon")
        if lat is None:
            continue
        if not (south <= lat <= north and west <= lon <= east):
            continue
        found.append(rel)
    return found


def fetch_geometry(ids: list[int]) -> dict[int, dict]:
    """Геометрия отношений одним запросом: relation(id:...); out geom;"""
    if not ids:
        return {}
    q = f"""
[out:json][timeout:240];
relation(id:{",".join(str(i) for i in ids)});
out tags geom;
"""
    return {el["id"]: el for el in overpass(q).get("elements", [])}


def rings_of(rel: dict) -> list[list[tuple[float, float]]]:
    """Внешние кольца отношения в формате (lon, lat) — как ждёт shapely."""
    rings = []
    for member in rel.get("members", []):
        if member.get("type") == "way" and member.get("role") in ("outer", "", None):
            geom = member.get("geometry") or []
            ring = [(p["lon"], p["lat"]) for p in geom]
            if len(ring) >= 4:
                rings.append(ring)
    return rings


def match_district(name_candidates: list[str], district_names: list[str]) -> str | None:
    """Сопоставить имя отношения OSM с каноническим названием района из КАТО."""
    keys = {norm_key(n) for n in name_candidates if n}
    for canonical in district_names:
        ck = norm_key(canonical)
        for k in keys:
            if k == ck or k.startswith(ck) or ck.startswith(k):
                return canonical
    return None


def from_geojson(path: str) -> dict:
    """Конвертировать GeoJSON с районами (сделан из OSM) в наш формат с кольцами.

    Зачем: в текущем OSM отношения районов городов республиканского значения стали
    «пустышками» (members: 0) — геометрия из публичных данных удалена. Поэтому берём
    открытый GeoJSON-экстракт, снятый с OSM до удаления, и честно указываем источник.
    """
    data = json.load(open(path, encoding="utf-8"))
    districts = []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        name = props.get("nameRu") or props.get("name")
        if not name:
            continue
        geom = feature.get("geometry", {})
        gt = geom.get("type")
        if gt == "Polygon":
            polygons = [geom["coordinates"]]
        elif gt == "MultiPolygon":
            polygons = geom["coordinates"]
        else:
            continue
        rings = [[(float(x), float(y)) for x, y, *_ in poly[0]] for poly in polygons if poly]
        rings = [r for r in rings if len(r) >= 4]
        if rings:
            districts.append({"name": name.replace(" район", "").strip(), "name_kk": None,
                              "osm_id": props.get("osm-relation-id"), "admin_level": "6", "rings": rings})
    return {"city": None, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "source": f"OSM (экстракт до удаления границ), файл {os.path.basename(path)}",
            "districts": districts}


def main() -> None:
    try:
        from shapely.geometry import Point, Polygon  # noqa: PLC0415
    except ImportError:
        print("Нужен shapely: pip install shapely", file=sys.stderr)
        raise SystemExit(1)

    # 1) города, по которым есть открытый GeoJSON-экстракт (Алматы и т.п.)
    for geo_path in sorted(glob.glob("data/source/*districts*.geo.json")):
        data = from_geojson(geo_path)
        guess = "Алматы" if "almaty" in os.path.basename(geo_path).lower() else None
        if not guess:
            continue
        data["city"] = guess
        os.makedirs("data/districts", exist_ok=True)
        out = os.path.join("data/districts", f"{guess}.json")
        json.dump(data, open(out, "w", encoding="utf-8"), ensure_ascii=False)
        print(f"[geojson] {guess}: районов {len(data['districts'])} -> {out} "
              f"(источник: {data['source']})")

    # 2) города, по которым пробуем взять геометрию прямо из OSM
    city_districts = json.load(open("data/city_districts.json", encoding="utf-8"))
    by_city: dict[str, list[str]] = {}
    for item in city_districts:
        by_city.setdefault(item["city"], []).append(item["name_ru"])

    bboxes = json.load(open("data/osm/_cities.json", encoding="utf-8"))
    out_dir = "data/districts"
    os.makedirs(out_dir, exist_ok=True)

    for city in REPUBLIC_CITIES:
        already = os.path.exists(os.path.join(out_dir, f"{city}.json"))
        if already:
            print(f"[skip] {city}: полигоны уже есть (см. above)")
            continue
        if city not in bboxes:
            print(f"[skip] {city}: нет bbox (сначала scripts/fetch_osm.py)")
            continue
        bbox = tuple(bboxes[city]["bbox"])          # (south, west, north, east)
        canonical_list = by_city.get(city, [])
        print(f"[search] {city}: ищем районы по именам из КАТО ({len(canonical_list)})…", flush=True)
        rels = find_relations(canonical_list, bbox)
        print(f"         кандидатов: {len(rels)}")

        # сопоставляем отношение -> каноническое имя
        chosen: dict[str, dict] = {}
        for rel in rels:
            tags = rel.get("tags", {})
            names = [tags.get("name"), tags.get("name:ru"), tags.get("name:kk")]
            canonical = match_district(names, canonical_list)
            if not canonical:
                continue
            level = int(str(tags.get("admin_level") or 99))
            if canonical in chosen and chosen[canonical]["level"] <= level:
                continue
            chosen[canonical] = {"id": rel["id"], "level": level, "name_kk": tags.get("name:kk")}

        missing = sorted(set(canonical_list) - set(chosen))
        if missing:
            print(f"         ! без полигонов: {missing}")

        geoms = fetch_geometry([c["id"] for c in chosen.values()])
        districts = []
        for canonical, info in chosen.items():
            rel = geoms.get(info["id"])
            rings = rings_of(rel) if rel else []
            if not rings:
                print(f"         ! {canonical}: нет геометрии, пропускаю")
                continue
            districts.append({"name": canonical, "name_kk": info["name_kk"],
                              "osm_id": info["id"], "admin_level": info["level"], "rings": rings})
            print(f"         + {canonical:20s} (osm {info['id']}, level {info['level']}, колец {len(rings)})")

        data = {"city": city, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "districts": districts}
        path = os.path.join(out_dir, f"{city}.json")
        json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False)
        print(f"[ok] {city}: районов с полигонами {len(districts)} -> {path}\n")


if __name__ == "__main__":
    main()
