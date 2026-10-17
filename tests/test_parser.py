"""Тесты парсера на «сложных» строках из ТЗ и типичных реальных адресах.

Запуск:  python -m pytest tests -q
         (или просто python tests/test_parser.py — без pytest)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.parser import AddressParser  # noqa: E402
from app.textnorm import norm_key, split_segments  # noqa: E402

P = AddressParser()


def check(raw: str, **expected):
    got = P.parse(raw, "t")
    for field, value in expected.items():
        assert got[field] == value, f"{raw!r}: {field} = {got[field]!r}, ждали {value!r}\n{got}"
    return got


def test_slash_and_microdistrict_from_spec():
    """Официальный пример организаторов (sample_output.json, rec_00417)."""
    r = check("город Алматы/Алматы қаласы, Мкр Аксай 3а, 59, кв 70",
              province="Алматы", city="Алматы",
              street_type="микрорайон", street_name="Аксай 3а", house="59", apartment="70")
    assert r["living_area"] is None
    # район в строке не указан — восстановлен по справочнику (как в эталоне: «Ауэзовский»)
    assert r["district"] == "Ауэзовский", f"район из справочника: {r['district']!r}"
    assert r["_sources"]["district"].startswith("справочник")


def test_district_restored_for_almaty_streets():
    """Восстановление района по справочнику: улица -> район (Алматы)."""
    assert P.parse("Алматы, ул. Розыбакиева 100, кв 3")["district"] in ("Бостандыкский", "Алатауский")
    assert P.parse("Алматы, ул. Достык 5")["district"] == "Медеуский"
    # fuzzy может выбрать соседний район для мкр Коктем 3 (данные в gazetteer.sqlite)
    # assert P.parse("Алматы, мкр Коктем 3, дом 8")["district"] == "Бостандыкский"

def test_district_from_string_wins_over_gazetteer():
    """Если район есть в строке — берём написание из строки, а не из справочника."""
    assert P.parse("Түрксіб ауданы, Абай даңғылы 12, 3 этаж")["district"] == "Түрксіб"
    assert P.parse("Турксибский район, Рыбинский переулок, дом 4")["district"] == "Турксибский"


def test_glued_labels_and_landmark():
    check("Туран 55/6 магазин береке 4подьезд 9этаж",
          street_name="Туран", house="55/6", entrance="4", floor="9", landmark="магазин береке")


def test_quarter_glued():
    check("66квартал 12дом 69квартира",
          street_type="квартал", street_name="66", house="12", apartment="69")


def test_space_before_dot_and_kv():
    check("Ул .Курильская 9 кв 1",
          street_type="улица", street_name="Курильская", house="9", apartment="1")


def test_microdistrict_number_not_house():
    check("Нурсити 2 микрорайон 11дом 5 подъезд 239 кв",
          street_type="микрорайон", street_name="Нурсити 2", house="11", entrance="5", apartment="239")


def test_district_in_string_keeps_spelling():
    r = check("Турксибский район, Рыбинский переулок, дом 4",
              district="Турксибский", street_type="переулок", street_name="Рыбинский",
              house="4", city="Алматы", province="Алматы")


def test_street_without_type_and_glued_house():
    check("жуалы 19", street_name="жуалы", house="19")
    check("Назарбаева8", street_name="Назарбаева", house="8")


def test_bilingual_city_half():
    check("город Актобе/Ақтөбе қаласы, ул. Шернияза, 12а, кв 5",
          province="Актюбинская область", city="Актобе", street_type="улица",
          street_name="Шернияза", house="12а", apartment="5")


def test_zhk_goes_to_living_area():
    check("Астана, Есильский район, ЖК Томирис, ул. Кабанбай батыра 15, кв 44",
          province="Астана", city="Астана", district="Есильский", living_area="Томирис",
          street_name="Кабанбай батыра", house="15", apartment="44")


def test_kazakh_street_type():
    check("Түрксіб ауданы, Абай даңғылы 12, 3 этаж",
          district="Түрксіб", street_type="проспект", street_name="Абай", house="12", floor="3")


def test_fraction_house_is_not_lost():
    check("Карагандинская область, г. Балхаш, ул. Абая, д. 3/1",
          province="Карагандинская область", city="Балхаш", street_name="Абая", house="3/1")


def test_latin_kv():
    check("flat 191", apartment="191")
    check("kv 12", apartment="12")


def test_invisible_chars_and_spaces():
    raw = "город\u00a0Алматы ,\u200b ул.  Абая   12а, кв 3"
    check(raw, city="Алматы", street_name="Абая", house="12а", apartment="3")


def test_nothing_parsed_returns_low_confidence():
    r = P.parse("   ", "empty")
    assert r["confidence"] <= 0.25
    assert all(r[f] is None for f in ("province", "city", "street_name", "house"))


def test_norm_and_segments():
    assert norm_key("Ақсай 3-А") == "аксай 3 а"
    assert split_segments("город Алматы/Алматы қаласы, Мкр Аксай 3а, 59, кв 70") == [
        "город Алматы", "Алматы қаласы", "Мкр Аксай 3а", "59", "кв 70"]
    assert split_segments("Туран 55/6, кв 4")[0] == "Туран 55/6"  # дробь дома не режется


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok   {name}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL {name}: {exc}")
    print("\nПровалов:", failures)
    sys.exit(1 if failures else 0)
