"""Интеграционные тесты REST API."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_health():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.anyio
async def test_parse_one():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/parse",
            json={
                "raw_address":
                    "Туран 55/6 магазин береке 4подьезд 9этаж"
            },
        )

    assert response.status_code == 200
    result = response.json()

    assert result["street_name"] == "Туран"
    assert result["house"] == "55/6"
    assert result["entrance"] == "4"
    assert result["floor"] == "9"
    assert result["landmark"].lower() == "магазин береке"
    assert 0 <= result["confidence"] <= 1


@pytest.mark.anyio
async def test_parse_batch():
    payload = {
        "addresses": [
            {
                "id": "1",
                "raw_address": "66квартал 12дом 69квартира",
            },
            {
                "id": "2",
                "raw_address":
                    "Нурсити 2 микрорайон 11дом 5подьезд 239 кв",
            },
        ]
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/parse/batch", json=payload)

    assert response.status_code == 200
    body = response.json()

    assert body["count"] == 2
    assert len(body["results"]) == 2
    assert body["results"][0]["house"] == "12"
    assert body["results"][0]["apartment"] == "69"
    assert body["results"][1]["house"] == "11"
    assert body["results"][1]["entrance"] == "5"
    assert body["results"][1]["apartment"] == "239"


@pytest.mark.anyio
async def test_empty_address_rejected():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/parse",
            json={"raw_address": "   "},
        )

    assert response.status_code == 422
