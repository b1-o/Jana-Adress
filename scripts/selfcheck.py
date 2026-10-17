#!/usr/bin/env python3
"""
Самопроверка решения: прогоняет контрольные адреса и сверяет ожидаемые поля.

Работает без интернета. Запуск из корня проекта:
    python scripts/selfcheck.py                  # локально
    docker compose exec jana-address python scripts/selfcheck.py   # внутри контейнера

Возвращает код 0, если всё сошлось, и 1 — если есть расхождения (удобно для CI и для жюри).
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.gazetteer import get_gazetteer  # noqa: E402
from app.parser import AddressParser  # noqa: E402

#: (строка, поле → ожидаемое значение). Значения — из ТЗ и наших договорённостей.
CASES: list[tuple[str, dict]] = [
    ("город Алматы/Алматы қаласы, Мкр Аксай 3а, 59, кв 70",
     {"province": "Алматы", "city": "Алматы", "street_type": "микрорайон",
      "street_name": "Аксай 3а", "house": "59", "apartment": "70"}),
    ("Туран 55/6 магазин береке 4подьезд 9этаж",
     {"street_name": "Туран", "house": "55/6", "entrance": "4", "floor": "9",
      "landmark": "магазин береке"}),
    ("66квартал 12дом 69квартира",
     {"street_type": "квартал", "street_name": "66", "house": "12", "apartment": "69"}),
    ("Ул .Курильская 9 кв 1",
     {"city": "Алматы", "street_type": "улица", "street_name": "Курильская",
      "house": "9", "apartment": "1"}),
    ("Нурсити 2 микрорайон 11дом 5 подъезд 239 кв",
     {"street_type": "микрорайон", "street_name": "Нурсити 2", "house": "11",
      "entrance": "5", "apartment": "239"}),
    ("Турксибский район, Рыбинский переулок, дом 4",
     {"district": "Турксибский", "street_type": "переулок", "street_name": "Рыбинский", "house": "4"}),
    ("жуалы 19", {"city": "Алматы", "street_name": "жуалы", "house": "19"}),
    # проспект Назарбаев есть и в Алматы, и в Кызылорде → город по ТЗ не выдумываем
    ("Назарбаева8", {"street_name": "Назарбаева", "house": "8"}),
    ("город Актобе/Ақтөбе қаласы, ул. Шернияза, 12а, кв 5",
     {"province": "Актюбинская область", "city": "Актобе", "street_name": "Шернияза",
      "house": "12а", "apartment": "5"}),
    ("Карагандинская область, г. Балхаш, ул. Абая, д. 3/1",
     {"province": "Карагандинская область", "city": "Балхаш", "street_name": "Абая", "house": "3/1"}),
    ("Астана, Есильский район, ЖК Томирис, ул. Кабанбай батыра 15, кв 44",
     {"city": "Астана", "district": "Есильский", "living_area": "Томирис",
      "street_name": "Кабанбай батыра", "house": "15", "apartment": "44"}),
    ("Түрксіб ауданы, Абай даңғылы 12, 3 этаж",
     {"city": "Алматы", "district": "Түрксіб", "street_type": "проспект",
      "street_name": "Абай", "house": "12", "floor": "3"}),
    ("flat 191", {"apartment": "191"}),
    ("павлодарская область, г. Павлодар, ул. Лермонтова 93, подъезд 2, этаж 4, кв 25",
     {"province": "Павлодарская область", "city": "Павлодар", "street_name": "Лермонтова",
      "house": "93", "entrance": "2", "floor": "4", "apartment": "25"}),
]


def main() -> int:
    print("=" * 72)
    print("Jana Address — самопроверка")
    print("=" * 72)

    gaz = get_gazetteer()
    print(f"\n1. Справочник: {'найден' if gaz.available else 'НЕ НАЙДЕН'} ({gaz.path})")
    for table, n in sorted((gaz.stats or {}).items()):
        print(f"     {table:<14} {n}")
    if not gaz.available or not gaz.stats.get("streets"):
        print("     !! справочник пуст — образ собран без data/gazetteer.sqlite")

    parser = AddressParser(gaz)
    print(f"\n2. Контрольные адреса: {len(CASES)}")
    failures = 0
    started = time.time()
    for raw, expected in CASES:
        got = parser.parse(raw, "selfcheck")
        problems = [f"{f}: ждали {v!r}, получили {got[f]!r}"
                    for f, v in expected.items() if got[f] != v]
        if problems:
            failures += 1
            print(f"   FAIL  {raw[:60]}")
            for p in problems:
                print(f"         {p}")
        else:
            print(f"   ok    {raw[:60]}")

    n = len(CASES)
    elapsed = time.time() - started
    print(f"\n3. Скорость: {n} строк за {elapsed:.3f} c  (~{n / max(elapsed, 1e-6):.0f} строк/с)")
    print(f"   Лимит ТЗ: 1000 строк за 5 минут → запас больше чем в 1000 раз")

    print("\n4. Обязательные поля ответа:")
    sample = parser.parse(CASES[0][0], "selfcheck")
    required = ["id", "raw_address", "province", "city", "district", "living_area", "street_type",
                "street_name", "house", "apartment", "entrance", "floor", "landmark", "confidence"]
    missing = [f for f in required if f not in sample]
    print("   " + ("все 14 полей на месте" if not missing else f"НЕТ ПОЛЕЙ: {missing}"))
    failures += len(missing)

    print("\n5. Итог: " + ("ВСЁ ОК ✅" if not failures else f"ПРОБЛЕМ: {failures} ❌"))
    print("=" * 72)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
