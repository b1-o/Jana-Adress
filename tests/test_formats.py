"""Регрессия на «грязные» написания адресов.

Каждый тест здесь — реальный дефект, который ломал разбор:
склейки, литера дома, казахские сокращения, ложные срабатывания.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.gazetteer import Gazetteer
from app.parser import AddressParser

DB = os.path.join(os.path.dirname(__file__), "..", "data", "gazetteer.sqlite")


@pytest.fixture(scope="module")
def parser():
    return AddressParser(Gazetteer(DB))


def test_type_without_space_after_dot(parser):
    """«ул.Абая» — тип должен отрезаться, даже если нет пробела после точки."""
    r = parser.parse("г.Алматы ул.Абая 12")
    assert r["street_type"] == "улица"
    assert r["street_name"] == "Абая"
    assert r["house"] == "12"


def test_fully_glued_address(parser):
    """«Алматыул.Абая12кв5» — без единого пробела."""
    r = parser.parse("Алматыул.Абая12кв5")
    assert r["city"] == "Алматы"
    assert r["street_name"] == "Абая"
    assert r["house"] == "12"
    assert r["apartment"] == "5"


def test_house_litera_does_not_stick_to_street(parser):
    """«Абая 12 А» — литера относится к дому, а не к названию улицы."""
    r = parser.parse("Алматы, Абая 12 А")
    assert r["street_name"] == "Абая"
    assert r["house"] == "12а"


def test_kz_short_street_type(parser):
    """«Абай к-сі» — казахское сокращение «көшесі»."""
    r = parser.parse("Алматы қ., Абай к-сі, 12")
    assert r["street_type"] == "улица"
    assert r["street_name"] == "Абай"
    assert r["house"] == "12"


def test_kz_short_avenue_type(parser):
    r = parser.parse("Алматы қаласы, Абай даңғ. 12")
    assert r["street_type"] == "проспект"
    assert r["street_name"] == "Абай"


def test_entrance_short_form(parser):
    """«п. 2» — сокращение подъезда, а не часть названия улицы."""
    r = parser.parse("Алматы, Абая 12, п.2, эт.3, кв.5")
    assert r["street_name"] == "Абая"
    assert r["entrance"] == "2"
    assert r["floor"] == "3"
    assert r["apartment"] == "5"


def test_zheltoksan_is_street_not_quarter(parser):
    """«Желтоқсан» содержит «тоқсан» (квартал) — не должно ломать улицу."""
    r = parser.parse("Кызылорда, Желтоқсан 10")
    assert r["street_name"] == "Желтоқсан"
    assert r["house"] == "10"
    assert r["street_type"] == "улица"


def test_real_quarter_still_works(parser):
    """А настоящий квартал обязан остаться кварталом."""
    r = parser.parse("Алматы, 66 квартал 12 дом 69 кв")
    assert r["street_type"] == "квартал"
    assert r["street_name"] == "66"
    assert r["house"] == "12"
    assert r["apartment"] == "69"


def test_living_area_hint_beats_foreign_street(parser):
    """Пришахтинск — жилмассив Караганды; «Толе батыра» есть и в Алматы."""
    r = parser.parse("Пришахтинск, ул. Толе батыра 5, 2 подъезд")
    assert r["city"] == "Караганда"
    assert r["province"] == "Карагандинская область"
    assert r["district"] == "Казыкекбийский" or r["district"] == "Казыбекбийский"
    assert r["street_name"] == "Толе батыра"


def test_mult_word_query_not_truncated_to_first_word(parser):
    """«Толе батыра» не должна превращаться в «Толе би» по первому слову."""
    r = parser.parse("Караганда, ул. Толе батыра 5")
    assert r["street_name"] == "Толе батыра"


def test_raw_address_is_verbatim(parser):
    """ТЗ: raw_address — дословно, несмотря на всю предобработку."""
    src = "г.Алматы ул.Абая 12, кв.5"
    r = parser.parse(src)
    assert r["raw_address"] == src
