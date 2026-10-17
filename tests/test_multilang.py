"""Тесты мультиязычного разбора: русский, казахский, английский.

Проверяем то, что чаще всего ломалось:
  * адрес на латинице не находил город и улицу;
  * казахские типы улиц (көшесі, даңғылы) не распознавались как тип;
  * микрорайон путался с улицей с таким же названием;
  * улица из другого города подменяла район.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.gazetteer import get_gazetteer  # noqa: E402
from app.lang import normalize_type_phrases, strip_admin_en, translit_latin  # noqa: E402
from app.parser import AddressParser  # noqa: E402
from app.textnorm import lookup_keys  # noqa: E402

P = AddressParser(get_gazetteer())


# ─────────────────────────── транслитерация ───────────────────────────

def test_transliteration_of_city_names():
    assert translit_latin("Almaty") == "алматы"
    assert translit_latin("Astana") == "астана"
    assert translit_latin("Shymkent") == "шымкент"
    assert translit_latin("Abai") == "абай"
    assert translit_latin("Abay") == "абай"
    assert translit_latin("Turan") == "туран"
    assert translit_latin("Karaganda") == "караганда"


def test_transliteration_handles_diphthongs():
    # «y» после гласной — й, после согласной — ы
    assert translit_latin("Kabanbay batyr") == "кабанбай батыр"
    assert translit_latin("Dostyk") == "достык"


def test_lookup_keys_add_cyrillic_variant():
    keys = lookup_keys("Almaty city")
    assert "алматы" in keys, keys


def test_strip_admin_words_before_transliteration():
    # «city» не должно превращаться в «киты»
    assert strip_admin_en("Almaty city") == "Almaty"
    assert strip_admin_en("Turan avenue") == "Turan"


def test_compound_type_phrases():
    assert "мкр" in normalize_type_phrases("Нурсити шағын ауданы 11")
    assert "шоссе" in normalize_type_phrases("Туран тас жолы 5")


# ─────────────────────────── города на латинице ───────────────────────────

def test_city_in_latin_is_recognised():
    for raw, city in [
        ("Almaty, Abai street 12", "Алматы"),
        ("Astana, Turan avenue 55/6", "Астана"),
        ("Shymkent, Zhibek zholy 44", "Шымкент"),
        ("Karaganda, Erubaeva street 21", "Караганда"),
    ]:
        r = P.parse(raw)
        assert r["city"] == city, f"{raw}: city={r['city']!r}, ждали {city!r}"


def test_english_street_types():
    cases = {
        "Almaty, Abai street 12": "улица",
        "Astana, Turan avenue 55/6": "проспект",
        "Aktobe, Alash avenue 5": "проспект",
    }
    for raw, stype in cases.items():
        r = P.parse(raw)
        assert r["street_type"] == stype, f"{raw}: {r['street_type']!r}, ждали {stype!r}"


def test_english_address_full_set():
    r = P.parse("Almaty city, Abai street 12, apt 5")
    assert r["province"] == "Алматы"
    assert r["city"] == "Алматы"
    assert r["street_name"] == "Abai"      # ТЗ: ровно как в строке
    assert r["house"] == "12"
    assert r["apartment"] == "5"


# ─────────────────────────── казахский ───────────────────────────

def test_kazakh_street_types():
    cases = {
        "Алматы қаласы, Абай көшесі 12": ("Алматы", "улица"),
        "Астана қаласы, Туран даңғылы 55/6": ("Астана", "проспект"),
        "Ақтөбе қаласы, Әл-Фараби даңғылы 7": ("Актобе", "проспект"),
    }
    for raw, (city, stype) in cases.items():
        r = P.parse(raw)
        assert r["city"] == city, f"{raw}: city={r['city']!r}"
        assert r["street_type"] == stype, f"{raw}: type={r['street_type']!r}"


def test_kazakh_and_russian_give_same_fields():
    ru = P.parse("Алматы, Абай көшесі 12")
    kz = P.parse("Алматы қаласы, Абай көшесі 12")
    assert ru["city"] == kz["city"] == "Алматы"
    assert ru["street_name"] == kz["street_name"] == "Абай"


# ─────────────────────────── микрорайоны ───────────────────────────

def test_microdistrict_before_and_after_type():
    assert P.parse("Алматы, мкр Аксай 3а 59")["house"] == "59"
    r = P.parse("Алматы, 4 микрорайон 12")
    assert r["street_name"] == "4", r
    assert r["house"] == "12", r


def test_microdistrict_not_replaced_by_street():
    """«Аксай 3а» — микрорайон Ауэзовского района, а не улица «Аксай»."""
    r = P.parse("город Алматы/Алматы қаласы, Мкр Аксай 3а, 59, кв 70")
    assert r["street_name"] == "Аксай 3а"
    assert r["district"] == "Ауэзовский", r["district"]


# ─────────────────────────── изоляция городов ───────────────────────────

def test_street_not_taken_from_another_city():
    """Улица «Абай» есть и в Шымкенте, но для Алматы должен вернуться Алматы."""
    from app.gazetteer import get_gazetteer as gg
    from app.textnorm import norm_key as nk
    row = gg().find_street(nk("Абай"), "Алматы")
    assert row is None or row["city"] == "Алматы", row


def test_no_city_in_string_still_parses_street():
    r = P.parse("Туран 55/6 магазин береке 4подьезд 9этаж")
    assert r["street_name"] == "Туран"
    assert r["house"] == "55/6"
    assert r["entrance"] == "4"
    assert r["floor"] == "9"
    assert r["landmark"]
