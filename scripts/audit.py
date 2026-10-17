"""Аудит точности разбора по корпусу data/audit_cases.json.

Считает метрику так же, как жюри (ТЗ, стр. 11):
  address   60% — область, город, название улицы, дом
  details   25% — квартира, подъезд, этаж
  reference 15% — район и жилой массив (только записи, где они есть в строке)

Поле, которого нет в эталоне, из подсчёта исключается.

    python scripts/audit.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.parser import AddressParser          # noqa: E402
from app.preprocessor import preprocess_address  # noqa: E402

GROUPS = {
    "address": ["province", "city", "street_name", "house"],
    "details": ["apartment", "entrance", "floor"],
    "reference": ["district", "living_area"],
}


def norm(value):
    """Сравнение как у жюри: нижний регистр, без пунктуации и лишних пробелов."""
    if value is None:
        return None
    text = str(value).lower().strip()
    text = re.sub(r"[.,;:!?«»\"'()]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def main() -> int:
    path = Path(__file__).resolve().parents[1] / "data" / "audit_cases.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    parser = AddressParser()

    stats = {field: [0, 0] for fields in GROUPS.values() for field in fields}
    fails = []

    for case in cases:
        result = parser.parse(preprocess_address(case["raw"]))
        for field in stats:
            expected = norm(case.get(field))
            if expected is None:
                continue
            stats[field][1] += 1
            if norm(result.get(field)) == expected:
                stats[field][0] += 1
            else:
                fails.append((case["raw"], field, case.get(field), result.get(field)))

    print(f"Записей в корпусе: {len(cases)}\n")
    print(f"{'поле':<14}{'верно':>7}{'всего':>7}{'точность':>10}")
    for field, (ok, total) in stats.items():
        if total:
            print(f"{field:<14}{ok:>7}{total:>7}{100 * ok / total:>9.1f}%")

    score = 0.0
    print()
    for name, fields in GROUPS.items():
        ok = sum(stats[f][0] for f in fields)
        total = sum(stats[f][1] for f in fields)
        acc = 100 * ok / total if total else 0.0
        weight = {"address": 0.60, "details": 0.25, "reference": 0.15}[name]
        score += acc * weight
        print(f"  {name:<10}{acc:>6.1f}% × {weight:.2f} = {acc * weight / 100:.3f}")

    print(f"\nИТОГОВЫЙ SCORE: {score:.1f}%")

    if fails:
        print(f"\nОшибки ({len(fails)}):")
        for raw, field, expected, got in fails:
            print(f"  [{field}] ждали {expected!r}, получили {got!r}   ← {raw}")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
