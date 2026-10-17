"""Область в прямом порядке и город в обратном порядке слов.

ТЗ (стр. 9): province — «название в прямом порядке: «Актюбинская область»,
«Алматы» для городов республиканского значения». КАТО отдаёт часть регионов
как «область Жетісу» и «область Ұлытау» — это нужно приводить к русской форме.

ТЗ (стр. 10): английский адрес «Almaty city, Abai street 12» — маркер города
стоит после названия, а не перед ним.
"""

import pytest

from app.parser import AddressParser
from app.preprocessor import preprocess_address

#: все 20 регионов: ни один не должен начинаться со слова «область»
REGIONS = [
    ("Акмолинская область", "Кокшетау"),
    ("Актюбинская область", "Актобе"),
    ("Алматинская область", "Конаев"),
    ("Атырауская область", "Атырау"),
    ("Восточно-Казахстанская область", "Усть-Каменогорск"),
    ("Жамбылская область", "Тараз"),
    ("Жетысуская область", "Талдыкорган"),
    ("Западно-Казахстанская область", "Уральск"),
    ("Карагандинская область", "Караганда"),
    ("Костанайская область", "Костанай"),
    ("Кызылординская область", "Кызылорда"),
    ("Мангистауская область", "Актау"),
    ("Павлодарская область", "Павлодар"),
    ("Северо-Казахстанская область", "Петропавловск"),
    ("Туркестанская область", "Туркестан"),
    ("Улытауская область", "Жезказган"),
    ("Абайская область", "Семей"),
]


@pytest.fixture(scope="module")
def parser():
    return AddressParser()


@pytest.mark.parametrize("expected, city", REGIONS)
def test_province_direct_order(parser, expected, city):
    """Область приходит в форме «<X>ская область», а не «область X»."""
    result = parser.parse(f"{city}, ул. Абая 5")
    assert result["province"] == expected
    assert not result["province"].lower().startswith("область")


@pytest.mark.parametrize("raw, expected", [
    ("Жетісу облысы, Талдықорған қаласы, Абай көшесі 5", "Жетысуская область"),
    ("Ұлытау облысы, Жезқазған, Абай көшесі 7", "Улытауская область"),
    ("Түркістан облысы, Түркістан қаласы, Абай көшесі 5", "Туркестанская область"),
    ("Павлодар облысы, Павлодар қаласы, Абай көшесі 5", "Павлодарская область"),
    ("Батыс Қазақстан облысы, Орал қаласы, Абай көшесі 5", "Западно-Казахстанская область"),
])
def test_province_from_kazakh(parser, raw, expected):
    """Казахское «<X> облысы» переводится в русскую форму."""
    assert parser.parse(raw)["province"] == expected


@pytest.mark.parametrize("raw", [
    "Almaty city, Abai street 12",
    "Astana city, Kabanbay batyr avenue 53",
    "Shymkent city, Tauke khan street 15",
])
def test_english_city_marker_after_name(parser, raw):
    """«<City> city» распознаётся: маркер стоит после названия."""
    result = parser.parse(preprocess_address(raw))
    assert result["city"] is not None


def test_details_before_street(parser):
    """Детали перед улицей не должны отбирать номер дома."""
    result = parser.parse(preprocess_address("подьезд 4 этаж 9 Туран 55/6"))
    assert result["house"] == "55/6"
    assert result["entrance"] == "4"
    assert result["floor"] == "9"
