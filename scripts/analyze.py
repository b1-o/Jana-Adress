#!/usr/bin/env python3
"""
Анализ набора адресов: что разобралось, что нет, чего не хватает в справочнике.

Нужен ровно в тот момент, когда организаторы пришлют train.json / sample_input.json:
на размеченном файле он показывает ошибки, на неразмеченном — покрытие и дырки в справочнике.

Запуск:
    python scripts/analyze.py data/train.json
    python scripts/analyze.py data/sample_input.json --expected data/sample_output.json
    python scripts/analyze.py data/train.json --out data/reports --top 30
    python scripts/analyze.py data/train.json --manual-hints data/manual/street_misses.json

Что выводит:
  • заполненность полей и распределение confidence;
  • строки, которые не разобрались вовсе (нет улицы и дома);
  • «остатки» — куски строки, которые парсер не смог отнести ни к одному полю;
  • улицы и города, которых нет в справочнике (это и есть список задач для OSM/ручных таблиц);
  • если дан эталон — общую метрику через scripts/eval.py;
  • файл-заготовку под ручное заполнение районов по проблемным улицам.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time
from collections import Counter
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.gazetteer import get_gazetteer  # noqa: E402
from app.parser import AddressParser  # noqa: E402
from app.textnorm import norm_key  # noqa: E402

FIELDS = ["province", "city", "district", "living_area", "street_type", "street_name",
          "house", "apartment", "entrance", "floor", "landmark"]


# --------------------------------------------------------------------------- ввод
def load_rows(path: str) -> list[dict]:
    """Понимает .json (список/«results»/«addresses»), .jsonl, .csv и .txt — форматы Jana Post
    и обычные списки строк."""
    raw = open(path, encoding="utf-8-sig", errors="replace").read()
    name = path.lower()
    if name.endswith(".jsonl"):
        rows = []
        for i, line in enumerate(raw.splitlines()):
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            rows.append({"id": item.get("id") or f"rec_{i:05d}",
                         "raw_address": item.get("raw_address") or str(item)})
        return rows
    if name.endswith(".json") or raw.lstrip()[:1] in "[{":
        data = json.loads(raw)
        if isinstance(data, dict):
            data = data.get("addresses") or data.get("records") or data.get("results") or []
        rows = []
        for i, item in enumerate(data):
            if isinstance(item, dict):
                rows.append({"id": item.get("id") or f"rec_{i:05d}",
                             "raw_address": item.get("raw_address") or item.get("address") or ""})
            else:
                rows.append({"id": f"rec_{i:05d}", "raw_address": str(item)})
        return rows
    first = raw.split("\n", 1)[0]
    if name.endswith(".csv") or "," in first:
        rows = []
        for i, r in enumerate(csv.DictReader(io.StringIO(raw))):
            addr = (r.get("raw_address") or r.get("address") or r.get("Адрес") or r.get("адрес")
                    or list(r.values())[-1])
            rows.append({"id": r.get("id") or f"rec_{i:05d}", "raw_address": addr or ""})
        return rows
    return [{"id": f"rec_{i:05d}", "raw_address": line.strip()}
            for i, line in enumerate(raw.splitlines()) if line.strip()]


# --------------------------------------------------------------------------- отчёт
def bucket(conf: float) -> str:
    if conf < 0.4:
        return "0.0–0.4 (почти не разобрано)"
    if conf < 0.6:
        return "0.4–0.6 (неуверенно)"
    if conf < 0.8:
        return "0.6–0.8 (норм)"
    return "0.8–1.0 (уверенно)"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="файл с адресами (train.json / sample_input.json / csv / txt)")
    ap.add_argument("--expected", help="эталон (sample_output.json) — если есть")
    ap.add_argument("--out", default="data/reports", help="куда сохранить отчёт")
    ap.add_argument("--top", type=int, default=25, help="сколько примеров показывать в топах")
    ap.add_argument("--manual-hints", help="сохранить заготовку ручных уточнений по улицам-промахам")
    args = ap.parse_args()

    rows = load_rows(args.input)
    gaz, parser = get_gazetteer(), AddressParser()
    started = time.time()
    results = [parser.parse(r["raw_address"], r["id"]) for r in rows]
    elapsed = max(time.time() - started, 1e-6)

    filled = Counter()
    for r in results:
        for f in FIELDS:
            if r.get(f):
                filled[f] += 1

    conf_buckets = Counter(bucket(r["confidence"] or 0) for r in results)
    unresolved = [r for r in results if not r["street_name"] and not r["house"]]
    no_street = [r for r in results if not r["street_name"] and r["house"]]
    leftovers = Counter(r["_leftover"] for r in results if r["_leftover"])

    # промахи справочника
    city_miss, street_miss = Counter(), Counter()
    for r in results:
        if r["city"] and not gaz.find_city(norm_key(r["city"]), strict=True):
            city_miss[(r["raw_address"], r["city"])] += 1
        if r["street_name"] and not (gaz.find_street(norm_key(r["street_name"]), r["city"])
                                     or gaz.find_street(norm_key(r["street_name"]))):
            street_miss[(r["city"], r["street_type"], r["street_name"])] += 1

    print(f"\n=== АНАЛИЗ {os.path.basename(args.input)} ===")
    print(f"строк: {len(rows)}   время: {elapsed:.2f} c   ({len(rows) / elapsed:.0f} строк/с)")

    print("\nЗаполненность полей:")
    for f in FIELDS:
        bar = "█" * int(30 * filled[f] / max(len(results), 1))
        print(f"  {f:<13} {filled[f]:>6}  {filled[f] / max(len(results), 1) * 100:5.1f}%  {bar}")

    print("\nУверенность:")
    for b in ("0.8–1.0 (уверенно)", "0.6–0.8 (норм)", "0.4–0.6 (неуверенно)", "0.0–0.4 (почти не разобрано)"):
        n = conf_buckets.get(b, 0)
        print(f"  {b:<26} {n:>6}  {n / max(len(results), 1) * 100:5.1f}%  {'█' * int(30 * n / max(len(results), 1))}")

    print(f"\nНе разобралось совсем (нет ни улицы, ни дома): {len(unresolved)} "
          f"({len(unresolved) / max(len(results), 1) * 100:.1f}%)")
    for r in unresolved[: args.top]:
        print(f"  · {r['raw_address'][:110]}")

    print(f"\nУлица не найдена, но дом есть: {len(no_street)}")
    for r in no_street[: min(args.top, 10)]:
        print(f"  · {r['raw_address'][:110]}")

    if leftovers:
        print(f"\nТоп «остатков» (что не отнесли ни к одному полю), {len(leftovers)} уник.:")
        for text, n in leftovers.most_common(args.top):
            print(f"  {n:>5}× {text[:100]}")

    if street_miss:
        print(f"\nУлицы, которых нет в справочнике: {len(street_miss)} уник. (это задачи для OSM/ручных таблиц)")
        for (city, stype, street), n in street_miss.most_common(args.top):
            print(f"  {n:>5}× [{city or '—'}] {stype or '—'} {street}")

    if city_miss:
        print(f"\nГорода, которых нет в справочнике: {len(city_miss)}")
        for (raw, city), n in city_miss.most_common(min(args.top, 10)):
            print(f"  {n:>5}× {city}   ← {raw[:80]}")

    # ------------------------------------------------------------------ файлы
    os.makedirs(args.out, exist_ok=True)
    base = os.path.splitext(os.path.basename(args.input))[0]
    report = {
        "input": args.input, "rows": len(rows), "seconds": round(elapsed, 3),
        "filled": dict(filled), "confidence_buckets": dict(conf_buckets),
        "unresolved": [r["raw_address"] for r in unresolved],
        "no_street": [r["raw_address"] for r in no_street],
        "leftovers": leftovers.most_common(200),
        "street_misses": [{"city": c, "street_type": t, "street_name": s, "count": n}
                          for (c, t, s), n in street_miss.most_common(500)],
        "city_misses": [{"city": c, "count": n, "raw": raw} for (raw, c), n in city_miss.most_common(200)],
    }
    path = os.path.join(args.out, f"analyze_{base}.json")
    json.dump(report, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nОтчёт: {path}")

    if args.manual_hints and street_miss:
        hints = []
        for (city, stype, street), n in street_miss.most_common(200):
            hints.append({
                "kind": "street",
                "name": street,
                "city": city,
                "street_type": stype,
                "district": None,          # ← заполнить руками: район города
                "aliases": [street],
                "_count": n,
            })
        json.dump(hints, open(args.manual_hints, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"Заготовка ручных уточнений: {args.manual_hints} ({len(hints)} улиц)")

    if args.expected:
        print("\n=== МЕТРИКА ПО ЭТАЛОНУ ===")
        from scripts.eval import evaluate, load  # noqa: PLC0415
        rep = evaluate(results, load(args.expected))
        for field, m in rep["per_field"].items():
            acc = f"{m['accuracy'] * 100:.1f}%" if m["accuracy"] is not None else "—"
            print(f"  {field:<13} верно {m['ok']:>5}  ошибок {m['bad']:>5}  точность {acc}")
        print(f"\n  ИТОГОВЫЙ SCORE: {rep['score'] * 100:.1f}%")
        json.dump(rep, open(os.path.join(args.out, f"eval_{base}.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
