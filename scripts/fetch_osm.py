#!/usr/bin/env python3
"""
Сбор справочника по OpenStreetMap (Overpass API) для Jana Address.

Что собираем по каждому городу:
  1. Районы города (relations boundary=administrative, admin_level 8..11)  -> полигоны
  2. Улицы (ways highway=* с именем)                                        -> имя + центр
  3. Жилые массивы / микрорайоны (nodes/ways place=suburb|neighbourhood|quarter|city_district)

Затем по point-in-polygon раскладываем улицы и микрорайоны по районам города.

Запуск:  python scripts/fetch_osm.py [--cities Алматы,Астана,Шымкент] [--out data/osm]
Требует: requests, shapely  (pip install requests shapely)
ВАЖНО: интернет нужен только на этапе подготовки справочника (по правилам хакатона
в финальном прогоне сеть отключается, поэтому результат кладём в репозиторий).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
UA = "jana-address-hackathon/0.2 (gazetteer builder; contact: team)"

# Города-миллионники и крупные центры — по ним наибольшая доля адресов.
DEFAULT_CITIES = [
    "Алматы", "Астана", "Шымкент", "Караганда", "Актобе", "Тараз",
    "Павлодар", "Усть-Каменогорск", "Семей", "Атырау", "Актау",
    "Костанай", "Кызылорда", "Уральск", "Петропавловск", "Туркестан",
    "Талдыкорган", "Темиртау", "Боралдай", "Конаев",
]


def http_json(url: str, params: dict, tries: int = 4, pause: float = 3.0):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(
                url + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA}
            )
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(pause * (i + 1))
    raise RuntimeError(f"failed {url}: {last}")


def overpass(query: str, tries: int = 4) -> dict:
    last = None
    for ep in OVERPASS_ENDPOINTS:
        for i in range(tries):
            try:
                data = urllib.parse.urlencode({"data": query}).encode()
                req = urllib.request.Request(ep, data=data, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=300) as r:
                    return json.load(r)
            except Exception as e:  # noqa: BLE001
                last = e
                sys.stderr.write(f"  ! {ep} try {i + 1}: {e}\n")
                time.sleep(5 * (i + 1))
    raise RuntimeError(f"overpass failed: {last}")


def nominatim_bbox(city: str, country: str = "Казахстан"):
    js = http_json(
        NOMINATIM,
        {"q": f"{city}, {country}", "format": "json", "limit": 1, "polygon_geojson": 0},
    )
    if not js:
        return None
    res = js[0]
    s, n, w, e = (float(x) for x in res["boundingbox"])  # S, N, W, E
    return {"city": city, "bbox": [s, w, n, e], "osm": res.get("osm_id"), "display": res.get("display_name")}


def fetch_city(city: str, info: dict) -> dict:
    s, w, n, e = info["bbox"]
    bbox = f"{s},{w},{n},{e}"

    # --- 1. районы города (полигоны) ---
    q_districts = f"""
[out:json][timeout:180];
(
  relation["boundary"="administrative"]["admin_level"~"^(8|9|10)$"]({bbox});
  relation["place"~"^(city_district|district|borough)$"]({bbox});
);
out tags geom;
"""
    # --- 2. улицы ---
    q_streets = f"""
[out:json][timeout:180];
(
  way["highway"]["name"]({bbox});
);
out tags center;
"""
    # --- 3. микрорайоны / жилые массивы / посёлки ---
    q_places = f"""
[out:json][timeout:180];
(
  node["place"~"^(suburb|neighbourhood|quarter|city_district|village|town|hamlet|residential)$"]({bbox});
  way["place"~"^(suburb|neighbourhood|quarter|residential)$"]({bbox});
  node["landuse"="residential"]["name"]({bbox});
  way["landuse"="residential"]["name"]({bbox});
);
out tags center;
"""

    districts_raw = overpass(q_districts).get("elements", [])
    time.sleep(2)
    streets_raw = overpass(q_streets).get("elements", [])
    time.sleep(2)
    places_raw = overpass(q_places).get("elements", [])
    time.sleep(2)

    return {
        "city": city,
        "bbox": info["bbox"],
        "districts": districts_raw,
        "streets": streets_raw,
        "places": places_raw,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def district_polygons(rel: dict):
    """Собрать список колец (списки точек lon/lat — порядок для shapely) из relation with geom."""
    rings = []
    for m in rel.get("members", []):
        if m.get("type") == "way" and m.get("role") in ("outer", "", None) and m.get("geometry"):
            ring = [(p["lon"], p["lat"]) for p in m["geometry"]]
            if len(ring) >= 4:
                rings.append(ring)
    return rings


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cities", default=",".join(DEFAULT_CITIES))
    ap.add_argument("--out", default="data/osm")
    args = ap.parse_args()

    try:
        from shapely.geometry import Point, Polygon  # noqa: PLC0415
    except ImportError:
        print("Нужен shapely: pip install shapely", file=sys.stderr)
        raise SystemExit(1)

    os.makedirs(args.out, exist_ok=True)
    cities = [c.strip() for c in args.cities.split(",") if c.strip()]

    # список городов с bbox (кешируем, чтобы не дёргать Nominatim повторно)
    cache_path = os.path.join(args.out, "_cities.json")
    cache = {}
    if os.path.exists(cache_path):
        cache = json.load(open(cache_path, encoding="utf-8"))

    for city in cities:
        out_path = os.path.join(args.out, f"{city}.json")
        if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
            print(f"[skip] {city}: уже есть {out_path}")
            continue
        if city not in cache:
            info = nominatim_bbox(city)
            if not info:
                print(f"[warn] Nominatim не нашёл {city}, пропускаю")
                continue
            cache[city] = info
            json.dump(cache, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            time.sleep(1.2)
        print(f"[fetch] {city} bbox={cache[city]['bbox']} ...", flush=True)
        try:
            data = fetch_city(city, cache[city])
        except Exception as e:  # noqa: BLE001
            print(f"[error] {city}: {e}")
            continue

        # --- раскладываем улицы/микрорайоны по районам (point-in-polygon) ---
        polys = []
        for rel in data["districts"]:
            tags = rel.get("tags", {})
            name = tags.get("name:ru") or tags.get("name") or tags.get("name:kk")
            if not name:
                continue
            for ring in district_polygons(rel):
                try:
                    poly = Polygon(ring)
                    if not poly.is_valid:
                        poly = poly.buffer(0)
                    if poly.is_empty or poly.area <= 0:
                        continue
                    polys.append({"name": name, "name_kk": tags.get("name:kk"),
                                  "admin_level": tags.get("admin_level"),
                                  "poly": poly})
                except Exception:  # noqa: BLE001
                    continue

        out_streets, out_places = [], []
        for st in data["streets"]:
            tags = st.get("tags", {})
            name = tags.get("name")
            c = st.get("center") or {}
            lat, lon = c.get("lat"), c.get("lon")
            if not name or lat is None:
                continue
            d = None
            p = Point(lon, lat)
            for item in polys:
                if item["poly"].contains(p):
                    d = item["name"]
                    break
            out_streets.append({
                "name": name, "name_kk": tags.get("name:kk"), "name_ru": tags.get("name:ru"),
                "lat": lat, "lon": lon, "district": d,
                "highway": tags.get("highway"),
                "osm_id": st.get("id"),
            })

        for pl in data["places"]:
            tags = pl.get("tags", {})
            name = tags.get("name")
            lat = pl.get("lat") or (pl.get("center") or {}).get("lat")
            lon = pl.get("lon") or (pl.get("center") or {}).get("lon")
            if not name or lat is None:
                continue
            d = None
            p = Point(lon, lat)
            for item in polys:
                if item["poly"].contains(p):
                    d = item["name"]
                    break
            out_places.append({
                "name": name, "name_kk": tags.get("name:kk"), "name_ru": tags.get("name:ru"),
                "place": tags.get("place") or ("residential" if tags.get("landuse") == "residential" else None),
                "lat": lat, "lon": lon, "district": d, "osm_id": pl.get("id"),
            })

        result = {
            "city": city,
            "bbox": data["bbox"],
            "fetched_at": data["fetched_at"],
            "districts": [
                {"name": (r.get("tags", {}).get("name:ru") or r.get("tags", {}).get("name")),
                 "name_kk": r.get("tags", {}).get("name:kk"),
                 "admin_level": r.get("tags", {}).get("admin_level"),
                 "osm_id": r.get("id")}
                for r in data["districts"]
            ],
            "streets": out_streets,
            "places": out_places,
        }
        json.dump(result, open(out_path, "w", encoding="utf-8"), ensure_ascii=False)
        n_d = sum(1 for s in out_streets if s["district"])
        print(f"[ok] {city}: улиц={len(out_streets)} (с районом {n_d}), "
              f"мест/мкр={len(out_places)}, районов={len(result['districts'])} -> {out_path}",
              flush=True)

    print("[done] OSM справочник собран")


if __name__ == "__main__":
    main()
