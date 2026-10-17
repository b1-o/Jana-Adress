"""Порядок «квартира / подъезд / этаж» не должен перемешиваться.

Раньше строка «115 кв 100 этаж 5 подъезд 4» разбиралась как подъезд 5,
этаж 4: форма «число + слово» находила «5 подъезд» раньше, чем «этаж 5»,
и забирала пятёрку у этажа.
"""

import pytest

from app.parser import AddressParser
from app.preprocessor import preprocess_address

CASES = [
    # (адрес, дом, квартира, подъезд, этаж)
    ("кожамкулова 115 кв 100 этаж 5 подъезд 4", "115", "100", "4", "5"),
    ("Кожамкулова 115, кв 100, 5 этаж, 4 подъезд", "115", "100", "4", "5"),
    ("Кожамкулова 115 кв.100, этаж 5, подъезд 4", "115", "100", "4", "5"),
    ("Алматы, мкр Аксай 3а 59, 4 этаж 2 подъезд 15 кв", "59", "15", "2", "4"),
    ("Караганда, Бухар жырау 25, 9 этаж 3 подъезд 77 кв", "25", "77", "3", "9"),
    ("Атырау, Азаттык 20, 4 этаж 2 подъезд 66 кв", "20", "66", "2", "4"),
    ("Туран 55/6 магазин береке 4подьезд 9этаж", "55/6", None, "4", "9"),
    ("11дом 4подьезд 9этаж 239кв", "11", "239", "4", "9"),
    ("Нурсити 2 микрорайон 11дом 5 подъезд 239 кв", "11", "239", "5", None),
    ("Алматы, Абая 12 этаж 5 подъезд 4", "12", None, "4", "5"),
    ("Алматы, Абая 12, кв 5, подъезд 2, этаж 7", "12", "5", "2", "7"),
    ("Алматы қаласы, Абай көшесі 12, 5 қабат, 4 кіреберіс, 100 пәтер",
     "12", "100", "4", "5"),
    ("Almaty, Abai street 12, floor 5, entrance 4, apt 100", "12", "100", "4", "5"),
    ("66квартал 12дом 69квартира", "12", "69", None, None),
    # «домм» — опечатка, «дом 100» не должно отдавать сотню этажу
    ("кожамкулова 117 кв 5 домм 100 этаж 6", "117", "5", None, "6"),
    ("кожамкулова 117 кв 5 дом 100 этаж 6", "117", "5", None, "6"),
]


@pytest.fixture(scope="module")
def parser():
    return AddressParser()


@pytest.mark.parametrize("raw,house,apartment,entrance,floor", CASES)
def test_details_do_not_swap(parser, raw, house, apartment, entrance, floor):
    result = parser.parse(preprocess_address(raw))
    assert result["house"] == house
    assert result["apartment"] == apartment
    assert result["entrance"] == entrance
    assert result["floor"] == floor


@pytest.mark.parametrize("raw,house,apartment,entrance,floor", CASES)
def test_details_same_without_preprocess(parser, raw, house, apartment, entrance, floor):
    result = parser.parse(raw)
    assert result["house"] == house
    assert result["apartment"] == apartment
    assert result["entrance"] == entrance
    assert result["floor"] == floor


@pytest.mark.parametrize("raw", [
    "кожамкулова 117 кв 5 домм 100 этаж 6",
    "кожамкулова 117 кв 5 дом 100 этаж 6",
])
def test_typo_house_word_does_not_stick_to_street(parser, raw):
    """Опечатка «домм» не должна попадать в название улицы."""
    result = parser.parse(preprocess_address(raw))
    assert result["street_name"] == "кожамкулова"
    assert "дом" not in (result["street_name"] or "")
