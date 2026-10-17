#!/usr/bin/env python3
"""
Метрика как у жюри: считаем точность по полям на своём наборе с эталоном.

Правила (из ТЗ «Как оцениваем»):
  • адресные поля (province, city, street_name, house) — вес 60%;
  • детали (apartment, entrance, floor) — 25%;
  • справочные поля (district, living_area) — 15%, и только по тем записям,
    где они есть в эталоне;
  • если поля нет ни в ответе, ни в эталоне — запись из подсчёта исключается;
  • сравнение посимвольное после нормализации: нижний регистр, без пунктуации
    и лишних пробелов; падежи и опечатки не прощаются.

Запуск:
    python scripts/eval.py --input data/sample_input.json --expected data/sample_output.json
    python scripts/eval.py --input data/sample_input.json --expected data/sample_output.json --pred pred.json
    python scripts/eval.py --api http://localhost:8000          # прогнать через живой API
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GROUPS = {
    "address": (["province", "city", "street_name", "house"], 0.60),
    "details": (["apartment", "entrance", "floor"], 0.25),
    "reference": (["district", "living_area"], 0.15),
}
ALL_FIELDS = ["province", "city", "district", "living_area", "street_type", "street_name",
              "house", "apartment", "entrance", "floor", "landmark"]


def norm(value) -> str | None:
    if value is None:
        return None
    s = str(value).lower().replace("ё", "е")
    s = re.sub(r"[^\wа-я\s]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def load(path: str) -> list[dict]:
    data = json.load(open(path, encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("results") or data.get("addresses") or []
    return [r if isinstance(r, dict) else {"raw_address": r} for r in data]


def evaluate(pred: list[dict], expected: list[dict]) -> dict:
    by_id = {str(r.get("id")): r for r in pred}
    by_raw = {}
    for r in pred:
        by_raw.setdefault(r.get("raw_address"), r)

    report: dict = {"per_field": {}, "groups": {}, "skipped": 0, "total": len(expected), "errors": []}
    for field in ALL_FIELDS:
        ok = bad = counted = restored = 0
        for exp in expected:
            got = by_id.get(str(exp.get("id"))) or by_raw.get(exp.get("raw_address"))
            if got is None:
                report["skipped"] += 1
                continue
            e, g = norm(exp.get(field)), norm(got.get(field))
            if e is None and g is None:
                continue                      # поля нет ни там, ни там — не считается
            if e is None:
                # поля нет в эталоне, а решение подняло его из справочника:
                # в метрику не входит, смотрим на защите (см. ТЗ)
                restored += 1
                continue
            counted += 1
            if e == g:
                ok += 1
            else:
                bad += 1
                if len(report["errors"]) < 25:
                    report["errors"].append({"id": exp.get("id"), "field": field,
                                             "expected": exp.get(field), "got": got.get(field),
                                             "raw_address": exp.get("raw_address")})
        report["per_field"][field] = {"ok": ok, "bad": bad, "counted": counted,
                                      "restored": restored,
                                      "accuracy": round(ok / counted, 4) if counted else None}

    total_score = 0.0
    for group, (fields, weight) in GROUPS.items():
        ok = sum(report["per_field"][f]["ok"] for f in fields)
        counted = sum(report["per_field"][f]["counted"] for f in fields)
        acc = ok / counted if counted else 0.0
        report["groups"][group] = {"fields": fields, "weight": weight, "ok": ok,
                                   "counted": counted, "accuracy": round(acc, 4),
                                   "contribution": round(acc * weight, 4)}
        total_score += acc * weight
    report["score"] = round(total_score, 4)
    report["restored_total"] = sum(m["restored"] for m in report["per_field"].values())
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data/sample_input.json")
    ap.add_argument("--expected", default="data/sample_output.json")
    ap.add_argument("--pred", help="готовый файл предсказаний (иначе считаем локальным парсером)")
    ap.add_argument("--api", help="URL API, например http://localhost:8000")
    ap.add_argument("--report", help="куда сохранить отчёт JSON")
    args = ap.parse_args()

    rows = load(args.input)
    started = time.time()
    if args.pred:
        pred = load(args.pred)
    elif args.api:
        import urllib.request
        body = json.dumps({"addresses": [{"id": r.get("id"), "raw_address": r.get("raw_address")}
                                         for r in rows]}).encode()
        req = urllib.request.Request(args.api.rstrip("/") + "/api/parse/batch", data=body,
                                     headers={"Content-Type": "application/json"})
        pred = json.load(urllib.request.urlopen(req, timeout=300))["results"]
    else:
        from app.parser import AddressParser
        parser = AddressParser()
        pred = [parser.parse(r.get("raw_address"), r.get("id")) for r in rows]
    elapsed = time.time() - started

    expected = load(args.expected)
    report = evaluate(pred, expected)
    report["records"] = len(rows)
    report["seconds"] = round(elapsed, 3)
    report["records_per_second"] = round(len(rows) / elapsed, 1) if elapsed else None

    print(f"\nЗаписей: {report['records']}   время: {report['seconds']} c "
          f"({report['records_per_second']}/c, лимит 1000 записей за 5 минут)")
    print("\n{:<14} {:>6} {:>6} {:>6} {:>6} {:>8}".format(
        "поле", "верно", "ошибок", "учтено", "из справ.", "точность"))
    for field in ALL_FIELDS:
        m = report["per_field"][field]
        acc = f"{m['accuracy'] * 100:.1f}%" if m["accuracy"] is not None else "—"
        print("{:<14} {:>6} {:>6} {:>6} {:>6} {:>8}".format(field, m["ok"], m["bad"], m["counted"],
                                                            m["restored"], acc))
    print("\nГруппы (веса как у жюри):")
    for group, m in report["groups"].items():
        print(f"  {group:<10} {m['accuracy'] * 100:5.1f}% × {m['weight']:.2f} = {m['contribution']:.3f}")
    print(f"\nИТОГОВЫЙ SCORE: {report['score'] * 100:.1f}%")

    if report["errors"]:
        print("\nПримеры ошибок:")
        for e in report["errors"][:12]:
            print(f"  [{e['field']}] {e['id']}: ждали {e['expected']!r}, получили {e['got']!r}  ← {e['raw_address'][:60]}")

    if args.report:
        json.dump(report, open(args.report, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\nОтчёт сохранён: {args.report}")


if __name__ == "__main__":
    main()
