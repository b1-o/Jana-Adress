"""Требования ТЗ, которые легко нарушить незаметно.

1. «На каждую входную запись должен быть ответ» — одна битая строка
   не должна ронять весь пакет.
2. Номер дома с литерой: «12а» и заглавное «12А» — один и тот же дом.
3. Название улицы не должно приниматься за город («Туран 55/6» —
   это улица Туран, а не посёлок Туран).
4. Порядок полей в ответе совпадает с ТЗ.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import FIELD_ORDER, app
from app.parser import AddressParser
from app.preprocessor import preprocess_address


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def parser():
    return AddressParser()


# ─────────────────────────────────────────── 1. ни одна запись не теряется
@pytest.mark.parametrize("payload", [
    [{"id": "1", "raw_address": None}],
    [{"id": "2"}],
    [{"id": "3", "raw_address": 12345}],
    [{}],
    [{"id": "4", "raw_address": ""}],
    [{"id": "5", "raw_address": "   "}],
    [{"id": "6", "raw_address": "!!! ??? ..."}],
])
def test_batch_never_fails_on_bad_record(client, payload):
    """ТЗ: «Пропускать записи нельзя — на каждую входную запись должен быть ответ»."""
    response = client.post("/api/parse/batch", json={"addresses": payload})
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == len(payload)


def test_batch_keeps_good_records_next_to_bad(client):
    payload = [
        {"id": "good-1", "raw_address": "Алматы, Абая 12"},
        {"id": "bad", "raw_address": None},
        {"id": "good-2", "raw_address": "жуалы 19"},
    ]
    results = client.post("/api/parse/batch", json={"addresses": payload}).json()["results"]
    assert [r["id"] for r in results] == ["good-1", "bad", "good-2"]
    assert results[0]["house"] == "12"
    assert results[1]["confidence"] == 0.0
    assert results[2]["street_name"] == "жуалы"


def test_empty_batch_is_ok(client):
    response = client.post("/api/parse/batch", json={"addresses": []})
    assert response.status_code == 200
    assert response.json()["count"] == 0


# ─────────────────────────────────────────── 2. литера в любом регистре
@pytest.mark.parametrize("raw", ["Абая 12а", "Абая 12А", "Абая12А", "Абая 12А кв 3"])
def test_house_letter_any_case(parser, raw):
    result = parser.parse(preprocess_address(raw))
    assert result["house"].lower() == "12а"
    assert result["street_name"] == "Абая"


# ─────────────────────────────────────────── 3. улица не становится городом
@pytest.mark.parametrize("raw, street", [
    ("Туран 55/6", "Туран"),
    ("Достык 78", "Достык"),
    ("Толе би 59", "Толе би"),
])
def test_street_not_taken_as_city(parser, raw, street):
    result = parser.parse(preprocess_address(raw))
    assert result["street_name"] == street
    assert result["city"] != street


def test_city_restored_from_dictionary(parser):
    """«Жуалы» есть только в Алматы — город восстанавливается по справочнику."""
    result = parser.parse(preprocess_address("жуалы 19"))
    assert result["city"] == "Алматы"
    assert result["street_name"] == "жуалы"


def test_ambiguous_street_does_not_become_its_own_city(parser):
    """«Абая», «Достык», «Толе би» есть в десятке городов — город не выдумываем."""
    for raw, street in (("Абая 12", "Абая"), ("Достык 78", "Достык"),
                        ("Толе би 59", "Толе би")):
        result = parser.parse(preprocess_address(raw))
        assert result["city"] != street, f"{raw}: улица принята за город"


# ─────────────────────────────────────────── 4. формат ответа
def test_field_order_matches_spec(client):
    expected = ["id", "raw_address", "province", "city", "district", "living_area",
                "street_type", "street_name", "house", "apartment", "entrance",
                "floor", "landmark", "confidence"]
    assert FIELD_ORDER == expected
    body = client.post("/api/parse", json={"raw_address": "Алматы, Абая 12"}).json()
    assert list(body.keys()) == expected
