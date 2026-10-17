"""REST API + веб-интерфейс Jana Address (кейс 1, Jana Post × Terricon Valley).

Эндпоинты:
    GET  /                      — интерфейс (вставить строку / загрузить файл, правка, выгрузка)
    GET  /api/health            — статус и статистика справочника
    POST /api/parse             — разбор одной строки
    POST /api/parse/batch       — пакетный разбор: JSON {"addresses": [...]} или файл (json/csv/txt)
    GET  /api/fields            — описание полей ответа (для интерфейса)
    GET  /api/gazetteer/lookup  — что знает справочник про строку (улица/мкр/город/район)

Запуск: uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import csv
import io
import json
import time
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .gazetteer import get_gazetteer
from .parser import AddressParser
from .textnorm import norm_key
from .logging_mw import LoggingMiddleware
from .preprocessor import preprocess_address
from .confidence import compute_confidence

app = FastAPI(
    title="Jana Address API",
    version="0.3.0",
    description="Разбор произвольной адресной строки (RU/KZ) на поля логистики. "
                "Работает автономно: справочник лежит внутри образа.",
)

gaz = get_gazetteer()
parser = AddressParser(gaz)

# Разрешаем запросы с любого источника (для локального UI)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FIELD_ORDER = [
    "id", "raw_address", "province", "city", "district", "living_area", "street_type",
    "street_name", "house", "apartment", "entrance", "floor", "landmark", "confidence",
]


class SingleRequest(BaseModel):
    raw_address: str
    id: str | None = None


class BatchRequest(BaseModel):
    addresses: list[dict[str, Any]]


def _public(row: dict, debug: bool = False) -> dict:
    out = {k: row.get(k) for k in FIELD_ORDER}
    if debug:
        out["_sources"] = row.get("_sources", {})
    return out


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse("app/static/index.html")


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "gazetteer": {"path": gaz.path, "available": gaz.available, "stats": gaz.stats,
                      "summary": gaz.describe()},
        "endpoints": ["/api/parse", "/api/parse/batch", "/api/gazetteer/lookup"],
    }


@app.get("/api/fields")
def fields() -> dict:
    return {
        "order": FIELD_ORDER,
        "descriptions": {
            "province": "Область или город респ. значения (прямой порядок: «Актюбинская область», «Алматы»)",
            "city": "Только название города/нас. пункта, без слов «город», «пос.»",
            "district": "Район без слова «район» («Илийский», «Ауэзовский»)",
            "living_area": "Микрорайон или ЖК, если улица указана отдельно",
            "street_type": "улица / проспект / микрорайон / переулок / квартал …",
            "street_name": "Название улицы без типа, ровно как в строке (падеж и опечатки сохраняем)",
            "house": "Номер дома с дробью и литерой: 1/2, 12а",
            "apartment": "Номер квартиры без слов «кв»",
            "entrance": "Номер подъезда без слова «подъезд»",
            "floor": "Номер этажа",
            "landmark": "Ориентир: «магазин Береке», «Qazpost Солнечный»",
            "confidence": "Оценка уверенности 0..1",
        },
    }


@app.post("/api/parse")
def parse_one(req: SingleRequest, debug: bool = Query(False)) -> dict:
    if not req.raw_address or not req.raw_address.strip():
        raise HTTPException(status_code=422, detail="raw_address обязателен")
    clean = preprocess_address(req.raw_address)
    result = parser.parse(clean, req.id)
    result["raw_address"] = req.raw_address
    conf = compute_confidence(result, result.get("_sources", {}))
    result["confidence"] = conf["score"]
    if debug:
        result["_warnings"] = conf["warnings"]
    return _public(result, debug)


def _parse_one(item: dict, debug: bool = False) -> dict:
    """Разобрать одну запись. Никогда не бросает исключение.

    Требование ТЗ: «Пропускать записи нельзя — на каждую входную запись
    должен быть ответ». Поэтому любая неожиданность в одной строке даёт
    объект с null и confidence 0, а не ошибку 500 на весь пакет.
    """
    raw = item.get("raw_address")
    if raw is None:
        raw = ""
    if not isinstance(raw, str):
        raw = str(raw)
    rec_id = item.get("id")
    try:
        res = parser.parse(preprocess_address(raw), rec_id)
        res["raw_address"] = raw
        conf = compute_confidence(res, res.get("_sources", {}))
        res["confidence"] = conf["score"]
        return _public(res, debug)
    except Exception:  # noqa: BLE001 — одна плохая строка не должна ломать пакет
        return {
            "id": rec_id, "raw_address": raw,
            "province": None, "city": None, "district": None, "living_area": None,
            "street_type": None, "street_name": None, "house": None,
            "apartment": None, "entrance": None, "floor": None, "landmark": None,
            "confidence": 0.0,
        }


@app.post("/api/parse/batch")
def parse_batch(req: BatchRequest, debug: bool = Query(False)) -> dict:
    rows = req.addresses or []
    started = time.time()
    results = [_parse_one(r if isinstance(r, dict) else {"raw_address": r}, debug) for r in rows]
    return {"results": results, "count": len(results), "seconds": round(time.time() - started, 3)}


def _rows_from_upload(filename: str, content: bytes) -> list[dict]:
    name = (filename or "").lower()
    text = content.decode("utf-8-sig", errors="replace")
    if name.endswith(".json") or text.lstrip().startswith(("[", "{")):
        data = json.loads(text)
        if isinstance(data, dict):
            data = data.get("addresses") or data.get("records") or data.get("results") or []
        rows = []
        for i, item in enumerate(data):
            if isinstance(item, dict):
                rows.append({"id": item.get("id") or f"rec_{i:05d}",
                             "raw_address": item.get("raw_address") or item.get("address") or ""})
            else:
                rows.append({"id": f"rec_{i:05d}", "raw_address": str(item)})
        return rows
    # CSV / TXT: ищем колонку с адресом
    if "," in text.split("\n", 1)[0] or name.endswith(".csv"):
        reader = csv.DictReader(io.StringIO(text))
        rows = []
        for i, r in enumerate(reader):
            addr = r.get("raw_address") or r.get("address") or r.get("Адрес") or r.get("адрес")
            if addr is None:
                addr = list(r.values())[-1]
            rows.append({"id": r.get("id") or f"rec_{i:05d}", "raw_address": addr or ""})
        return rows
    return [{"id": f"rec_{i:05d}", "raw_address": line.strip()}
            for i, line in enumerate(text.splitlines()) if line.strip()]


@app.post("/api/parse/batch/upload")
async def parse_batch_upload(file: UploadFile = File(...), debug: bool = Query(False)) -> dict:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="пустой файл")
    try:
        rows = _rows_from_upload(file.filename or "", content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"не удалось прочитать файл: {exc}") from exc
    started = time.time()
    results = [_parse_one(r, debug) for r in rows]
    low = sum(1 for r in results if (r["confidence"] or 0) < 0.6)
    return {"results": results, "count": len(results), "low_confidence": low,
            "seconds": round(time.time() - started, 3)}


@app.get("/api/gazetteer/lookup")
def gazetteer_lookup(q: str = Query(..., min_length=2)) -> dict:
    key = norm_key(q)
    out: dict[str, Any] = {"query": q, "norm_key": key}
    for name, fn in (("province", gaz.find_province), ("city", gaz.find_city),
                     ("street", gaz.find_street), ("living_area", gaz.find_living_area),
                     ("district", gaz.find_district)):
        row = fn(key)
        out[name] = dict(row) if row else None
    return out


@app.exception_handler(Exception)
async def unhandled(_, exc: Exception) -> JSONResponse:  # pragma: no cover
    return JSONResponse(status_code=500, content={"detail": f"internal error: {exc}"})


app.mount("/static", StaticFiles(directory="app/static"), name="static")
