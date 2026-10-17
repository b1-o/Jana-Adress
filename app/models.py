"""
Схема таблиц Jana Address Database.
SQLite, автономная, внутри Docker-образа.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional


DB_PATH = Path(__file__).resolve().parent.parent / "data" / "jana_address.db"

SCHEMA = """
-- Регионы (области + города респ. значения)
CREATE TABLE IF NOT EXISTS provinces (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name_ru   TEXT    NOT NULL UNIQUE,
    name_kz   TEXT DEFAULT '',
    name_en   TEXT DEFAULT '',
    code_kato TEXT DEFAULT ''
);

-- Города / населенные пункты
CREATE TABLE IF NOT EXISTS cities (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    province_id INTEGER REFERENCES provinces(id),
    name_ru     TEXT    NOT NULL,
    name_kz     TEXT DEFAULT '',
    name_en     TEXT DEFAULT '',
    code_kato   TEXT DEFAULT '',
    type        TEXT DEFAULT 'city' CHECK(type IN ('city','town','village','settlement')),
    lat         REAL,
    lon         REAL
);

-- Районы городов
CREATE TABLE IF NOT EXISTS districts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    city_id     INTEGER REFERENCES cities(id),
    name_ru     TEXT    NOT NULL UNIQUE,
    name_kz     TEXT DEFAULT '',
    code_kato   TEXT DEFAULT ''
);

-- Улицы
CREATE TABLE IF NOT EXISTS streets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    city_id       INTEGER REFERENCES cities(id),
    name_ru       TEXT    NOT NULL,
    type_ru       TEXT DEFAULT ''  -- улица, проспект, микрорайон...
    normalized    TEXT    NOT NULL  -- lower, без пробелов, для поиска
);

-- Жилые массивы / микрорайоны / ЖК
CREATE TABLE IF NOT EXISTS living_areas (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    city_id INTEGER REFERENCES cities(id),
    name_ru TEXT NOT NULL,
    type    TEXT DEFAULT 'microdistrict'
);

-- Источники данных (для отладки/аудита)
CREATE TABLE IF NOT EXISTS data_sources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    url         TEXT DEFAULT '',
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    row_count   INTEGER DEFAULT 0
);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_cities_name ON cities(name_ru);
CREATE INDEX IF NOT EXISTS idx_cities_province ON cities(province_id);
CREATE INDEX IF NOT EXISTS idx_districts_city ON districts(city_id);
CREATE INDEX IF NOT EXISTS idx_streets_city ON streets(city_id);
CREATE INDEX IF NOT EXISTS idx_streets_normalized ON streets(normalized);
CREATE INDEX IF NOT EXISTS idx_living_areas_city ON living_areas(city_id);

-- Полнотекстовый поиск по улицам (для нечеткого матчинга)
CREATE VIRTUAL TABLE IF NOT EXISTS streets_fts USING fts5(
    name_ru,
    type_ru,
    content='streets',
    content_rowid='id'
);

-- Триггер: при INSERT/UPDATE в streets -> обновить FTS
CREATE TRIGGER IF NOT EXISTS trg_streets_ai AFTER INSERT ON streets BEGIN
    INSERT INTO streets_fts(rowid, name_ru, type_ru) VALUES (new.id, new.name_ru, new.type_ru);
END;

CREATE TRIGGER IF NOT EXISTS trg_streets_au AFTER UPDATE ON streets BEGIN
    UPDATE streets_fts SET name_ru = new.name_ru, type_ru = new.type_ru WHERE rowid = new.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_streets_ad AFTER DELETE ON streets BEGIN
    DELETE FROM streets_fts WHERE rowid = old.id;
END;
"""


def get_connection() -> sqlite3.Connection:
    """Соединение с БД (создаёт файл если нет)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  -- быстрее чтение/запись
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: Optional[sqlite3.Connection] = None) -> None:
    """Создать все таблицы и индексы."""
    c = conn or get_connection()
    c.executescript(SCHEMA)
    if not conn:
        c.close()


def db_stats(conn: Optional[sqlite3.Connection] = None) -> dict:
    """Статистика наполнения БД."""
    c = conn or get_connection()
    stats = {}
    for table in ("provinces", "cities", "districts", "streets", "living_areas"):
        row = c.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
        stats[table] = row["cnt"] if row else 0
    if not conn:
        c.close()
    return stats
