"""
Репозиторий Jana Address Database.
Все запросы к БД — через этот модуль.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
from unidecode import unidecode

from .models import get_connection, init_db, db_stats, DB_PATH

# Нормализация ключа для поиска
_RE_SPACES = re.compile(r'\s+')
_RE_PUNCT = re.compile(r'[^\w\d]')


def norm_key(text: str) -> str:
    """Нормализовать строку для поиска: lower + транслит + без пробелов."""
    if not text:
        return ""
    t = text.lower().strip()
    t = _RE_SPACES.sub('', t)
    t = _RE_PUNCT.sub('', t)
    # добавляем транслитерацию для латиницы
    trans = unidecode(t).lower()
    return f"{t}|{trans}"


class AddressRepository:
    """Репозиторий адресных данных."""

    def __init__(self, conn: Optional[sqlite3.Connection] = None):
        self._conn = conn or get_connection()

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()

    # ---- Province ----

    def find_provinces(self, query: str, limit: int = 5) -> List[Dict]:
        key = norm_key(query)
        rows = self._conn.execute(
            "SELECT * FROM provinces WHERE name_ru LIKE ? OR name_kz LIKE ? LIMIT ?",
            (f'%{query}%', f'%{query}%', limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_province_by_id(self, pid: int) -> Optional[Dict]:
        row = self._conn.execute("SELECT * FROM provinces WHERE id=?", (pid,)).fetchone()
        return dict(row) if row else None

    def add_province(self, name_ru: str, **kw) -> int:
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO provinces (name_ru, name_kz, name_en, code_kato) VALUES (?,?,?,?)",
            (name_ru, kw.get('name_kz', ''), kw.get('name_en', ''), kw.get('code_kato', ''))
        )
        return cur.lastrowid

    # ---- City ----

    def find_cities(self, query: str, limit: int = 10) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT c.*, p.name_ru as province_name FROM cities c "
            "LEFT JOIN provinces p ON c.province_id=p.id "
            "WHERE c.name_ru LIKE ? OR c.name_kz LIKE ? ORDER BY c.type DESC LIMIT ?",
            (f'%{query}%', f'%{query}%', limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def find_city_by_street(self, street_name: str, street_type: str = '') -> Optional[Dict]:
        """Найти город по имени улицы (если уникальная)."""
        key = norm_key(street_name)
        row = self._conn.execute(
            "SELECT DISTINCT c.* FROM streets s "
            "JOIN cities c ON s.city_id=c.id "
            "WHERE s.normalized=? LIMIT 1", (key,)
        ).fetchone()
        return dict(row) if row else None

    def add_city(self, name_ru: str, province_id: int = None, **kw) -> int:
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO cities (name_ru, name_kz, province_id, type, lat, lon) "
            "VALUES (?,?,?,?,?,?)",
            (name_ru, kw.get('name_kz', ''), province_id,
             kw.get('type', 'city'), kw.get('lat'), kw.get('lon'))
        )
        return cur.lastrowid

    # ---- District ----

    def find_districts(self, city_id: int, query: str = '') -> List[Dict]:
        if query:
            rows = self._conn.execute(
                "SELECT * FROM districts WHERE city_id=? AND name_ru LIKE ?",
                (city_id, f'%{query}%')
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM districts WHERE city_id=?", (city_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def add_district(self, name_ru: str, city_id: int, **kw) -> int:
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO districts (name_ru, name_kz, city_id) VALUES (?,?,?)",
            (name_ru, kw.get('name_kz', ''), city_id)
        )
        return cur.lastrowid

    # ---- Street ----

    def find_streets(self, query: str, city_id: int = None, limit: int = 10) -> List[Dict]:
        """Точный + FTS поиск."""
        results = []
        # 1. Точный по normalized
        q = norm_key(query)
        sql = ("SELECT s.*, c.name_ru as city_name FROM streets s "
               "JOIN cities c ON s.city_id=c.id WHERE s.normalized LIKE ?")
        params: Tuple = (f'%{q}%',)
        if city_id:
            sql += " AND s.city_id=?"
            params += (city_id,)
        sql += " LIMIT ?"
        params += (limit,)
        results.extend(dict(r) for r in self._conn.execute(sql, params).fetchall())

        # 2. FTS для нечеткого (если мало результатов)
        if len(results) < 3:
            fts_rows = self._conn.execute(
                "SELECT s.*, c.name_ru as city_name FROM streets_fts fts "
                "JOIN streets s ON s.id=fts.rowid "
                "JOIN cities c ON s.city_id=c.id "
                "WHERE streets_fts MATCH ? LIMIT ?",
                (f'"{query.split()[0]}*"', limit)
            ).fetchall()
            existing_ids = {r['id'] for r in results}
            for r in fts_rows:
                if dict(r)['id'] not in existing_ids:
                    results.append(dict(r))
        return results[:limit]

    def add_street(self, name_ru: str, city_id: int, type_ru: str = '', **kw) -> int:
        normalized = norm_key(name_ru)
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO streets (name_ru, type_ru, normalized, city_id) VALUES (?,?,?,?)",
            (name_ru, type_ru, normalized, city_id)
        )
        return cur.lastrowid

    # ---- Living Area ----

    def find_living_areas(self, query: str, city_id: int = None, limit: int = 10) -> List[Dict]:
        sql = "SELECT * FROM living_areas WHERE name_ru LIKE ?"
        params: Tuple = (f'%{query}%',)
        if city_id:
            sql += " AND city_id=?"
            params += (city_id,)
        sql += " LIMIT ?"
        params += (limit,)
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def add_living_area(self, name_ru: str, city_id: int, **kw) -> int:
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO living_areas (name_ru, city_id, type) VALUES (?,?,?)",
            (name_ru, city_id, kw.get('type', 'microdistrict'))
        )
        return cur.lastrowid

    # ---- Batch import ----

    def batch_import_provinces(self, data: List[Dict]) -> int:
        count = 0
        for row in data:
            rid = self.add_province(row.get('name', ''), **{
                k: v for k, v in row.items() if k != 'name'
            })
            if rid: count += 1
        self._conn.commit()
        return count

    def batch_import_cities(self, data: List[Dict]) -> int:
        count = 0
        for row in data:
            rid = self.add_city(
                row.get('name', ''),
                province_id=row.get('province_id'),
                **{k: v for k, v in row.items() if k not in ('name', 'province_id')}
            )
            if rid: count += 1
        self._conn.commit()
        return count

    def batch_import_streets(self, data: List[Dict]) -> int:
        count = 0
        for row in data:
            rid = self.add_street(
                row.get('name', ''),
                city_id=row.get('city_id', 0),
                type=row.get('type', ''),
            )
            if rid: count += 1
        self._conn.commit()
        return count

    # ---- Source tracking ----

    def log_source(self, name: str, url: str = '', desc: str = '', row_count: int = 0):
        self._conn.execute(
            "INSERT INTO data_sources (name, description, url, row_count) VALUES (?,?,?,?)",
            (name, desc, url, row_count)
        )
        self._conn.commit()

    def get_sources(self) -> List[Dict]:
        return [dict(r) for r in self._conn.execute("SELECT * FROM data_sources ORDER BY imported_at DESC").fetchall()]


# Глобальный инстанс (singleton pattern)
_repo: Optional[AddressRepository] = None


def get_repo() -> AddressRepository:
    global _repo
    if _repo is None:
        init_db()
        _repo = AddressRepository(get_connection())
    return _repo
