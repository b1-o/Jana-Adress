"""Проверка языков и точности разбора адресов.

Что делает:
  1. Берёт набор адресов на русском, казахском и английском (+ смешанные и «грязные»).
  2. Прогоняет каждый через тот же конвейер, что и боевой API:
     preprocess_address -> AddressParser.parse
  3. Считает:
     * «заполнено» — сколько полей из 14 вернулись непустыми;
     * «точно»     — сколько проверяемых полей совпали с ожидаемыми
                     (сравнение как у жюри: нижний регистр, без пунктуации и лишних пробелов);
     * метрику ТЗ  — address 60 % / details 25 % / reference 15 %;
     * среднюю уверенность (confidence) по группе.
  4. Печатает таблицу по языкам и общий итог.

Работает офлайн, интернет не нужен.

Запуск из папки проекта:
    python scripts/lang_check.py            # кратко
    python scripts/lang_check.py --verbose  # по каждой строке
    python scripts/lang_check.py --only kk  # только казахский
    python scripts/lang_check.py --json     # вывод в JSON

Свои примеры можно добавить в data/lang_cases.json:
    [{"group": "ru", "raw": "улица Абая 12, кв 5", "city": "Алматы", "street_name": "Абая", "house": "12", "apartment": "5"}]
Ожидаемые поля писать не обязательно — тогда строка попадёт только в статистику «заполнено».
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.parser import AddressParser            # noqa: E402
from app.preprocessor import preprocess_address  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# Группы языков
# ─────────────────────────────────────────────────────────────────────────────

GROUPS = {
    "ru": "русский",
    "kk": "казахский",
    "en": "английский (латиница)",
    "mix": "смешанный / двуязычный",
    "dirty": "опечатки, мусор, спецсимволы",
    "other": "другие языки — НЕ поддерживаются",
}

#: Что система реально понимает. Всё остальное разбирается частично или никак.
SUPPORTED = (
    "русский            — «улица Абая 12, кв 5»",
    "казахский          — «Абай даңғылы 12», «қаласы», «ауданы», «пәтер», «кіреберіс», «қабат»",
    "латиница/английский— «Almaty, Abay avenue 12, flat 5» (транслитерация в кириллицу)",
    "смешанный          — «город Алматы/Алматы қаласы, Мкр Аксай 3а, 59, кв 70»",
    "НЕ поддерживается  — турецкий, немецкий, узбекский, китайский, арабский и др.",
)

# Все 14 полей ответа по ТЗ.
FIELDS = [
    "raw_address", "province", "city", "district", "street_type", "street_name",
    "house", "apartment", "entrance", "floor", "living_area", "house_type",
    "confidence", "source",
]

# Поля, которые участвуют в метрике жюри.
METRIC = {
    "address": ["province", "city", "street_name", "house"],
    "details": ["apartment", "entrance", "floor"],
    "reference": ["district", "living_area"],
}
METRIC_WEIGHT = {"address": 0.60, "details": 0.25, "reference": 0.15}

# ─────────────────────────────────────────────────────────────────────────────
# Встроенные примеры
# ─────────────────────────────────────────────────────────────────────────────

CASES: list[dict] = [
    # --- русский -----------------------------------------------------------
    {"group": "ru", "raw": "город Алматы, Мкр Аксай 3а, 59, кв 70",
     "city": "Алматы", "district": "Ауэзовский", "street_type": "микрорайон",
     "street_name": "Аксай 3а", "house": "59", "apartment": "70"},
    {"group": "ru", "raw": "Алматы, улица Курильская 12, квартира 4",
     "city": "Алматы", "street_name": "Курильская", "house": "12", "apartment": "4"},
    {"group": "ru", "raw": "Астана, проспект Кабанбай батыра 21, подъезд 3, этаж 7, кв 45",
     "city": "Астана", "street_name": "Кабанбай батыра", "house": "21",
     "entrance": "3", "floor": "7", "apartment": "45"},
    {"group": "ru", "raw": "Шымкент, улица Туран 55/6",
     "city": "Шымкент", "street_name": "Туран", "house": "55/6"},
    {"group": "ru", "raw": "Алматы, Турксибский район, улица Абая 5",
     "city": "Алматы", "district": "Турксибский", "street_name": "Абая", "house": "5"},
    {"group": "ru", "raw": "Алматы, микрорайон Орбита-2, дом 14, кв 88",
     "city": "Алматы", "street_type": "микрорайон", "street_name": "Орбита-2",
     "house": "14", "apartment": "88"},
    {"group": "ru", "raw": "Караганда, проспект Бухар-Жырау 49, офис 12",
     "city": "Караганда", "street_name": "Бухар-Жырау", "house": "49"},
    {"group": "ru", "raw": "Караганда, район имени Казыбек би, улица Ержанова 12",
     "city": "Караганда", "street_name": "Ержанова", "house": "12"},
    {"group": "ru", "raw": "Актобе, 12 микрорайон, дом 7, квартира 3",
     "city": "Актобе", "street_type": "микрорайон", "street_name": "12",
     "house": "7", "apartment": "3"},
    {"group": "ru", "raw": "Алматы, улица Байтурсынова 15/1",
     "city": "Алматы", "street_name": "Байтурсынова", "house": "15/1"},
    {"group": "ru", "raw": "Карагандинская область, г. Балхаш, ул. Абая, д. 3/1",
     "province": "Карагандинская область", "city": "Балхаш",
     "street_name": "Абая", "house": "3/1"},
    {"group": "ru", "raw": "Алматы, улица Жандосова 2, подъезд 1, этаж 5, квартира 20",
     "city": "Алматы", "street_name": "Жандосова", "house": "2",
     "entrance": "1", "floor": "5", "apartment": "20"},

    # --- казахский ---------------------------------------------------------
    {"group": "kk", "raw": "Алматы қаласы, Әл-Фараби даңғылы 5, 3 пәтер",
     "city": "Алматы", "street_type": "проспект", "street_name": "Әл-Фараби",
     "house": "5", "apartment": "3"},
    {"group": "kk", "raw": "Астана қ., Қабанбай батыр даңғылы 21, 45 пәтер",
     "city": "Астана", "street_name": "Қабанбай батыр", "house": "21", "apartment": "45"},
    {"group": "kk", "raw": "Алматы қаласы, Абай даңғылы 12",
     "city": "Алматы", "street_type": "проспект", "street_name": "Абай", "house": "12"},
    {"group": "kk", "raw": "Шымкент қаласы, Тәуке хан даңғылы 3",
     "city": "Шымкент", "street_name": "Тәуке хан", "house": "3"},
    {"group": "kk", "raw": "Тараз қ., Төле би көшесі 59",
     "city": "Тараз", "street_name": "Төле би", "house": "59"},
    {"group": "kk", "raw": "Алматы қаласы, Жуалы көшесі 19",
     "city": "Алматы", "street_name": "Жуалы", "house": "19"},
    {"group": "kk", "raw": "Ақтөбе қаласы, Әбілқайыр хан даңғылы 40",
     "city": "Актобе", "street_name": "Әбілқайыр хан", "house": "40"},
    {"group": "kk", "raw": "Қарағанды қ., Бұқар жырау даңғылы 49",
     "city": "Караганда", "street_name": "Бұқар жырау", "house": "49"},
    {"group": "kk", "raw": "Алматы қ., Нұрсити шағын ауданы 11, 2 пәтер",
     "city": "Алматы", "street_type": "микрорайон", "street_name": "Нұрсити",
     "house": "11", "apartment": "2"},
    {"group": "kk", "raw": "Астана қ., Сарыарқа даңғылы 8, 3 кіреберіс, 5 қабат",
     "city": "Астана", "street_name": "Сарыарқа", "house": "8", "entrance": "3", "floor": "5"},
    {"group": "kk", "raw": "Алматы қ., Түрксіб ауданы, Абай даңғылы 12, 3 қабат",
     "city": "Алматы", "district": "Түрксіб", "street_name": "Абай", "house": "12", "floor": "3"},
    {"group": "kk", "raw": "Ақтөбе облысы, Қандыағаш қ., Абылай хан көшесі 7",
     "province": "Актюбинская область", "city": "Кандыагаш",
     "street_name": "Абылай хан", "house": "7"},

    # --- английский (латиница) ---------------------------------------------
    {"group": "en", "raw": "Almaty, Abay avenue 12, flat 5",
     "city": "Алматы", "street_type": "проспект", "street_name": "Abay",
     "house": "12", "apartment": "5"},
    {"group": "en", "raw": "Astana city, Kabanbay batyr avenue 21, apt 45",
     "city": "Астана", "street_name": "Kabanbay batyr", "house": "21", "apartment": "45"},
    {"group": "en", "raw": "Shymkent, Tauke Khan avenue 3",
     "city": "Шымкент", "street_name": "Tauke Khan", "house": "3"},
    {"group": "en", "raw": "Almaty, Rozybakiyev street 100, apartment 12",
     "city": "Алматы", "street_name": "Rozybakiyev", "house": "100", "apartment": "12"},
    {"group": "en", "raw": "Almaty city, Bostandyk district, Zhandosova street 2, unit 20",
     "city": "Алматы", "district": "Бостандыкский", "street_name": "Zhandosova",
     "house": "2", "apartment": "20"},
    {"group": "en", "raw": "Almaty, Almaly district, Abay avenue 12",
     "city": "Алматы", "district": "Алмалинский", "street_name": "Abay", "house": "12"},
    {"group": "en", "raw": "Karaganda, Bukhar Zhyrau avenue 49",
     "city": "Караганда", "street_name": "Bukhar Zhyrau", "house": "49"},
    {"group": "en", "raw": "Aktobe, Abulkhair Khan avenue 40, floor 4, flat 18",
     "city": "Актобе", "street_name": "Abulkhair Khan", "house": "40",
     "floor": "4", "apartment": "18"},
    {"group": "en", "raw": "Ivanova 5 flat 191",
     "street_name": "Ivanova", "house": "5", "apartment": "191"},

    # --- смешанный / двуязычный -------------------------------------------
    {"group": "mix", "raw": "город Алматы/Алматы қаласы, Мкр Аксай 3а, 59, кв 70",
     "city": "Алматы", "district": "Ауэзовский", "street_type": "микрорайон",
     "street_name": "Аксай 3а", "house": "59", "apartment": "70"},
    {"group": "mix", "raw": "город Актобе/Ақтөбе қаласы, ул. Шернияза, 12а, кв 5",
     "city": "Актобе", "street_name": "Шернияза", "house": "12а", "apartment": "5"},
    {"group": "mix", "raw": "Алматы, Abay көшесі 12, кв 5",
     "city": "Алматы", "street_name": "Abay", "house": "12", "apartment": "5"},
    {"group": "mix", "raw": "Almaty қаласы, улица Жандосова 2, floor 5, кв 20",
     "city": "Алматы", "street_name": "Жандосова", "house": "2", "floor": "5", "apartment": "20"},
    {"group": "mix", "raw": "Астана/Astana, проспект Мәңгілік Ел 12",
     "city": "Астана", "street_name": "Мәңгілік Ел", "house": "12"},

    # --- опечатки, мусор, спецсимволы -------------------------------------
    {"group": "dirty", "raw": "Абая 12 kv 5", "street_name": "Абая", "house": "12", "apartment": "5"},
    {"group": "dirty", "raw": "Назарбаева8", "street_name": "Назарбаева", "house": "8"},
    {"group": "dirty", "raw": "66квартал 12дом 69квартира",
     "street_type": "квартал", "street_name": "66", "house": "12", "apartment": "69"},
    {"group": "dirty", "raw": "11дом 4подьезд 9этаж 239кв",
     "house": "11", "entrance": "4", "floor": "9", "apartment": "239"},
    {"group": "dirty", "raw": "  Ул .Курильская  12 ,  кв 4 ",
     "street_name": "Курильская", "house": "12", "apartment": "4"},
    {"group": "dirty", "raw": "Алматы,\u200b улица\u00a0Абая\u200e 12,\ufeff кв 5",
     "city": "Алматы", "street_name": "Абая", "house": "12", "apartment": "5"},
    {"group": "dirty", "raw": "Нурсити 2 микрорайон 11дом 5 подъезд 239 кв",
     "street_type": "микрорайон", "house": "11", "entrance": "5", "apartment": "239"},
    {"group": "dirty", "raw": "магазин береке"},
    {"group": "dirty", "raw": "Qazpost Солнечный"},
    {"group": "dirty", "raw": "асфальт 3"},
    {"group": "dirty", "raw": ""},

    # --- другие языки: система их НЕ знает, проверяем только «не упало» ----
    # Ожидания здесь минимальные и объективные: дом/город, которые обязаны
    # находиться независимо от языка. Всё остальное legitimately остаётся пустым.
    {"group": "other", "raw": "Almatı, Abay caddesi 12, daire 5", "house": "12"},
    {"group": "other", "raw": "Almaty, Abay Straße 12, Wohnung 5", "city": "Алматы", "house": "12"},
    {"group": "other", "raw": "Almaty, Abay ko'chasi 12", "city": "Алматы", "house": "12"},
    {"group": "other", "raw": "Алматы, Абая көчөсү 12", "city": "Алматы", "house": "12"},
    {"group": "other", "raw": "阿拉木图市阿拜街12号"},
    {"group": "other", "raw": "ألماتي، شارع أباي ١٢"},
    {"group": "other", "raw": "アルマトイ市アバイ通り12"},
]

# ─────────────────────────────────────────────────────────────────────────────
# Сравнение как у жюри
# ─────────────────────────────────────────────────────────────────────────────

def norm(value) -> str | None:
    """Нижний регистр, без пунктуации и лишних пробелов (ТЗ, стр. 11)."""
    if value is None:
        return None
    text = str(value).lower().strip()
    text = re.sub(r"[.,;:!?«»\"'()]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def filled(result: dict) -> int:
    """Сколько полей вернулись непустыми (confidence и source не считаем)."""
    return sum(
        1 for f in FIELDS
        if f not in ("confidence", "source") and result.get(f) not in (None, "")
    )


def load_cases() -> list[dict]:
    """Встроенные примеры + data/lang_cases.json, если он есть."""
    cases = list(CASES)
    extra = ROOT / "data" / "lang_cases.json"
    if extra.exists():
        try:
            cases.extend(json.loads(extra.read_text(encoding="utf-8")))
        except Exception as exc:  # noqa: BLE001
            print(f"! Не смог прочитать {extra}: {exc}")
    return cases


# ─────────────────────────────────────────────────────────────────────────────
# Основной прогон
# ─────────────────────────────────────────────────────────────────────────────

def run(verbose: bool, only: str | None, as_json: bool) -> int:
    parser = AddressParser()
    cases = load_cases()
    if only:
        cases = [c for c in cases if c.get("group") == only]
        if not cases:
            print(f"! Нет примеров группы '{only}'. Доступны: {', '.join(GROUPS)}")
            return 1

    start = time.perf_counter()
    rows = []
    for case in cases:
        raw = case.get("raw", "")
        result = parser.parse(preprocess_address(raw))

        expected = {k: v for k, v in case.items() if k not in ("group", "raw")}
        checks = [(f, expected[f], result.get(f)) for f in expected]
        hits = [f for f, exp, got in checks if norm(got) == norm(exp)]

        # метрика ТЗ по этой строке
        group_stats = {}
        for gname, fields in METRIC.items():
            total = ok = 0
            for f in fields:
                if f not in expected:
                    continue
                total += 1
                ok += norm(result.get(f)) == norm(expected[f])
            group_stats[gname] = (ok, total)

        rows.append({
            "group": case.get("group", "?"),
            "raw": raw,
            "result": result,
            "expected": expected,
            "checks": checks,
            "hits": hits,
            "filled": filled(result),
            "metric": group_stats,
        })
    elapsed = time.perf_counter() - start

    if as_json:
        print(json.dumps([{
            "group": r["group"], "raw": r["raw"], "filled": r["filled"],
            "expected_hits": len(r["hits"]), "expected_total": len(r["checks"]),
            "result": r["result"],
        } for r in rows], ensure_ascii=False, indent=2))
        return 0

    W = 78
    print("=" * W)
    print("ПРОВЕРКА ЯЗЫКОВ И ТОЧНОСТИ — Jana Address")
    print("=" * W)
    print("Какие языки поддерживает система:")
    for line in SUPPORTED:
        print("   " + line)

    by_group: dict[str, list] = {}
    for r in rows:
        by_group.setdefault(r["group"], []).append(r)

    order = [g for g in GROUPS if g in by_group] + [g for g in by_group if g not in GROUPS]

    for g in order:
        items = by_group[g]
        n = len(items)
        avg_fill = sum(i["filled"] for i in items) / n
        parsed = sum(1 for i in items if i["filled"] >= 3)
        conf = [i["result"].get("confidence") or 0 for i in items]
        avg_conf = sum(conf) / len(conf) if conf else 0
        tot_ok = sum(len(i["hits"]) for i in items)
        tot_chk = sum(len(i["checks"]) for i in items)

        print()
        print(f"── {GROUPS.get(g, g)}  ({n} строк) " + "─" * max(1, W - len(GROUPS.get(g, g)) - len(str(n)) - 12))
        print(f"   разобрано (≥3 полей): {parsed}/{n}"
              f"   средняя уверенность: {avg_conf:.2f}"
              f"   полей в ответе в среднем: {avg_fill:.1f}")
        if tot_chk:
            print(f"   сверка с ожидаемым:   {tot_ok}/{tot_chk}"
                  f"  ({100 * tot_ok / tot_chk:.0f} %)")

        if verbose:
            for i in items:
                r = i["result"]
                print()
                print(f"   » {i['raw']!r}")
                print(f"     область : {r.get('province')}")
                print(f"     город   : {r.get('city')}")
                print(f"     район   : {r.get('district')}")
                print(f"     жилмассив: {r.get('living_area')}")
                print(f"     улица   : {r.get('street_type') or ''} {r.get('street_name') or ''}".rstrip())
                print(f"     дом     : {r.get('house')}   кв {r.get('apartment')}"
                      f"   под {r.get('entrance')}   эт {r.get('floor')}")
                print(f"     уверенность: {r.get('confidence')}   заполнено полей: {i['filled']}")
                bad = [(f, exp, got) for f, exp, got in i["checks"] if norm(got) != norm(exp)]
                for f, exp, got in bad:
                    print(f"     ✗ {f}: ожидали {exp!r}, получили {got!r}")

    # общий итог по метрике ТЗ
    print()
    print("=" * W)
    print("ИТОГ")
    print("-" * W)
    tot_ok = sum(len(i["hits"]) for i in rows)
    tot_chk = sum(len(i["checks"]) for i in rows)
    parsed = sum(1 for i in rows if i["filled"] >= 3)
    all_conf = [i["result"].get("confidence") or 0 for i in rows]

    print(f"   строк проверено          : {len(rows)}")
    print(f"   разобрано (≥3 полей)     : {parsed}/{len(rows)}"
          f"  ({100 * parsed / len(rows):.0f} %)")
    if tot_chk:
        print(f"   точность по сверке полей : {tot_ok}/{tot_chk}"
              f"  ({100 * tot_ok / tot_chk:.1f} %)")
    print(f"   средняя уверенность      : {sum(all_conf) / len(all_conf):.2f}")

    # метрика ТЗ
    parts = []
    for gname, fields in METRIC.items():
        ok = sum(i["metric"][gname][0] for i in rows)
        total = sum(i["metric"][gname][1] for i in rows)
        share = 100 * ok / total if total else 0
        parts.append((gname, ok, total, share))
        print(f"   {gname:<10} {METRIC_WEIGHT[gname]:>4.0%}"
              f"  : {ok}/{total} = {share:.1f} %")
    score = sum(METRIC_WEIGHT[g] * (ok / total if total else 0) for g, ok, total, _ in parts)
    print(f"   оценка по метрике ТЗ     : {100 * score:.1f} %")
    print(f"   время прогона            : {elapsed:.2f} с")
    print()
    print("   Полный аудит точности на корпусе жюри:  python scripts/audit.py")
    print("   Оценка по официальным примерам:        python scripts/eval.py")
    print("=" * W)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Проверка языков и точности разбора")
    ap.add_argument("--verbose", action="store_true", help="показать разбор каждой строки")
    ap.add_argument("--only", choices=list(GROUPS), help="только одна группа языков")
    ap.add_argument("--json", dest="as_json", action="store_true", help="вывод в JSON")
    args = ap.parse_args()
    return run(args.verbose, args.only, args.as_json)


if __name__ == "__main__":
    raise SystemExit(main())
