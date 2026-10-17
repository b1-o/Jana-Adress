"""Регрессионные тесты на разбор района (`district`).

Что тут закреплено — три реальных дефекта, найденных проверкой языков:

1. Район читался из строки ТОЛЬКО когда город не распознан: блок поиска района
   был вложен в ветку «город без маркера». «Алматы, Турксибский район, ...»
   терял район, а потом его подменял район из справочника по улице.
2. Разбор падал с TypeError на «Алматы, Турксибский район»: ``\\b`` в Python
   срабатывает и внутри строки пробелов, оставшейся после вырезанного города,
   поэтому в группу попадал ``None``.
3. Район, написанный латиницей («Bostandyk district»), возвращался латиницей,
   хотя эталон жюри — в русской графике («Бостандыкский»).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.gazetteer import get_gazetteer  # noqa: E402
from app.main import app  # noqa: E402
from app.parser import AddressParser  # noqa: E402
from app.preprocessor import preprocess_address  # noqa: E402

P = AddressParser(get_gazetteer())


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def parse(raw: str) -> dict:
    return P.parse(preprocess_address(raw))


# ───────────── 1. район вместе с городом в одной строке ─────────────

@pytest.mark.parametrize("raw, city, district", [
    ("Алматы, Турксибский район, улица Абая 5", "Алматы", "Турксибский"),
    ("Алматы қ., Түрксіб ауданы, улица Абая 5", "Алматы", "Түрксіб"),
    ("Астана, Есильский район, ул. Кабанбай батыра 15, кв 44", "Астана", "Есильский"),
    ("Шымкент, Абайский район, улица Дулати 5", "Шымкент", "Абайский"),
    ("Алматы, район Бостандыкский, улица Жандосова 2", "Алматы", "Бостандыкский"),
])
def test_district_is_read_even_when_city_is_present(raw, city, district):
    """Район из строки важнее района, который справочник подскажет по улице."""
    r = parse(raw)
    assert r["city"] == city
    assert r["district"] == district, f"{raw}: district={r['district']!r}, ждали {district!r}"
    # район взят из строки, а не подсказан справочником по улице
    assert r["_sources"].get("district", "").startswith("raw")


def test_district_without_word_rayon_in_output():
    """ТЗ: в поле `district` не должно быть слова «район»."""
    for raw in ("Алматы, Турксибский район, улица Абая 5",
                "Астана, Есильский район, ул. Кабанбай батыра 15"):
        district = parse(raw)["district"] or ""
        assert "район" not in district.lower(), raw


# ───────────── 2. обратный порядок: «район имени Казыбек би» ─────────────

@pytest.mark.parametrize("raw", [
    "Караганда, район имени Казыбек би, улица Ержанова 12",
    "Караганда, район им. Казыбек би, проспект Бухар-Жырау 49",
])
def test_reverse_order_district_with_lowercase_second_word(raw):
    """Второе слово названия района бывает со строчной буквы — «Казыбек би»."""
    r = parse(raw)
    assert r["city"] == "Караганда"
    assert (r["district"] or "").lower().startswith("казыбек би"), r["district"]
    assert r["street_name"] in ("Ержанова", "Бухар-Жырау")
    assert r["house"] in ("12", "49")


def test_bare_word_rayon_is_not_a_district():
    """«Талдыкорган, район, улица Назарбаева 5» — названия района нет, поле пустое."""
    r = parse("Талдыкорган, район, улица Назарбаева 5")
    assert r["city"] == "Талдыкорган"
    assert r["district"] is None
    assert r["street_name"] == "Назарбаева"


# ───────────── 3. район на латинице ─────────────

@pytest.mark.parametrize("raw, district", [
    ("Almaty city, Bostandyk district, Zhandosova street 2, unit 20", "Бостандыкский"),
    ("Almaty, Almaly district, Abay avenue 12", "Алмалинский"),
    ("Almaty, Medeu district, Dostyk avenue 5", "Медеуский"),
])
def test_latin_district_returns_cyrillic_canonical(raw, district):
    """Эталон жюри хранит район в русской графике — латиницу приводим к ней."""
    r = parse(raw)
    assert r["city"] == "Алматы"
    assert r["district"] == district, f"{raw}: district={r['district']!r}, ждали {district!r}"


def test_cyrillic_district_spelling_is_preserved():
    """Кириллическое написание из строки не трогаем: «Түрксіб» остаётся «Түрксіб»."""
    assert parse("Түрксіб ауданы, Абай даңғылы 12, 3 этаж")["district"] == "Түрксіб"


# ───────────── разбор не падает на «город, район» ─────────────

@pytest.mark.parametrize("raw", [
    "Алматы, Турксибский район",
    "Алматы, Турксибский район, улица Абая 5",
    "Астана, район Сарыарка",
    "Шымкент, Абайский район, улица Дулати 5, кв 3",
    "Алматы, Алмалинский район, проспект Абая 12, подъезд 2, этаж 5, кв 30",
])
def test_city_plus_district_does_not_crash(raw):
    """Раньше здесь был TypeError: 'NoneType' object is not subscriptable."""
    r = parse(raw)
    assert isinstance(r, dict)
    assert r["raw_address"] == raw
    assert r["city"] is not None


def test_batch_with_city_and_district_returns_every_row(client):
    """Пакет с районами не теряет строки и не падает целиком (ТЗ: ответ на каждую запись)."""
    raws = [
        "Алматы, Турксибский район, улица Абая 5",
        "Астана, Есильский район, ЖК Томирис, ул. Кабанбай батыра 15, кв 44",
        "Almaty city, Bostandyk district, Zhandosova street 2, unit 20",
        "Караганда, район имени Казыбек би, улица Ержанова 12",
        None,
    ]
    payload = [{"id": f"r{i}", "raw_address": r} for i, r in enumerate(raws)]
    resp = client.post("/api/parse/batch", json={"addresses": payload})
    assert resp.status_code == 200
    body = resp.json()
    out = body["results"]
    assert body["count"] == len(out) == 5
    assert [r["id"] for r in out] == [f"r{i}" for i in range(5)]
    assert out[0]["district"] == "Турксибский"
    assert out[2]["district"] == "Бостандыкский"
    assert out[4]["confidence"] == 0.0

