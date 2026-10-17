"""Доступ к справочнику (SQLite) + алиасы + fuzzy с индексом.

Скоростная часть (индекс по первым буквам + LRU-кэш fuzzy) — от сокомандника.
Поверх неё:
  * трёхъязычный поиск: латиница транслитерируется в кириллицу
    («Abai» -> «абай», «Almaty» -> «алматы»), казахские буквы уже
    приводятся к русским в norm_key();
  * изоляция города: если город известен, улица и жилмассив ищутся
    ТОЛЬКО в нём — иначе «Абай» из Шымкента подменял район в Алматы;
  * префиксный откат: «улица Абая» находит «Абай даңғылы» (падежное
    окончание не даёт точного ключа).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from collections import defaultdict
from typing import Optional, Any, List, Dict

from .textnorm import norm_key, stem_key, search_keys
from .fuzzy import fuzzy_find

DEFAULT_PATH = os.environ.get("GAZETTEER_PATH", "data/gazetteer.sqlite")


class AliasRow(dict):
    def __getitem__(self, key: str) -> Any:
        return super().get(key)


class Gazetteer:
    def __init__(self, path: str = DEFAULT_PATH):
        self.path = path
        self.available = os.path.exists(path)
        self._local = threading.local()
        self.stats: dict = {}

        # --- индексы для быстрого поиска ---
        self._city_index: Dict[str, List[str]] = defaultdict(list)   # первые 2 буквы -> [города]
        self._street_index: Dict[str, List[str]] = defaultdict(list)
        self._living_index: Dict[str, List[str]] = defaultdict(list)

        # полные списки для fallback
        self._all_cities: List[str] = []
        self._all_streets: List[str] = []
        self._all_living: List[str] = []

        # индекс улиц по городам: город -> {первые 2 буквы -> [названия]}
        # нужен, чтобы fuzzy не выходил за пределы города
        self._city_street_index: Dict[str, Dict[str, List[str]]] = {}
        self._city_living_index: Dict[str, Dict[str, List[str]]] = {}
        self._city_weight: Dict[str, int] = {}

        # LRU-кэш для fuzzy результатов
        self._fuzzy_cache: Dict[str, tuple] = {}
        self._FUZZY_CACHE_SIZE = 5000

        if self.available:
            conn = self._conn()
            for table in ("provinces", "cities", "districts", "settlements", "streets",
                          "living_areas", "city_districts"):
                try:
                    self.stats[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                except sqlite3.Error:
                    self.stats[table] = 0

            try:
                # Загружаем и индексируем
                for name in [r[0] for r in conn.execute("SELECT name FROM cities").fetchall()]:
                    self._all_cities.append(name)
                    self._city_index[_prefix(norm_key(name))].append(name)

                for name in [r[0] for r in conn.execute("SELECT name FROM streets").fetchall()]:
                    self._all_streets.append(name)
                    self._street_index[_prefix(norm_key(name))].append(name)

                for name in [r[0] for r in conn.execute("SELECT name FROM living_areas").fetchall()]:
                    self._all_living.append(name)
                    self._living_index[_prefix(norm_key(name))].append(name)

                # «вес» города: сколько улиц про него знает справочник. Нужен,
                # когда в строке города нет: «Абая 12» есть и в Алматы, и в Таразе,
                # и выбирать нужно самый ходовой вариант, а не случайный.
                for city, cnt in conn.execute(
                        "SELECT city, COUNT(*) FROM streets GROUP BY city").fetchall():
                    if city:
                        self._city_weight[city] = cnt
            except sqlite3.Error:
                pass

        # --- алиасы ---
        self._aliases: dict[str, dict] = {}
        for ap in [os.path.join(os.path.dirname(path) if path else ".", "aliases.json"), "data/aliases.json"]:
            if os.path.exists(ap):
                try:
                    with open(ap, "r", encoding="utf-8") as af:
                        raw = json.load(af)
                    for k, v in raw.items():
                        self._aliases[norm_key(k)] = v
                    break
                except Exception:
                    pass

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def _query(self, sql: str, args: tuple) -> list:
        if not self.available:
            return []
        try:
            return self._conn().execute(sql, args).fetchall()
        except sqlite3.Error:
            return []

    def _first(self, sql: str, args: tuple) -> Optional[Any]:
        rows = self._query(sql, args)
        return rows[0] if rows else None

    # === fuzzy ===
    def _city_names(self, city: str, table: str) -> List[str]:
        """Список названий улиц (или жилмассивов) одного города — с кэшем."""
        cache = self._city_street_index if table == "streets" else self._city_living_index
        if city not in cache:
            rows = self._query(f"SELECT name FROM {table} WHERE city=?", (city,))
            names = [r[0] for r in rows]
            idx: Dict[str, List[str]] = defaultdict(list)
            for n in names:
                idx[_prefix(norm_key(n))].append(n)
            cache[city] = idx
        return cache[city]

    def _fuzzy_lookup(self, query: str, index: Dict[str, List[str]],
                      full_list: Optional[List[str]] = None, kind: str = "") -> tuple:
        """Быстрый fuzzy: фильтруем по индексу первых букв, потом ищем в подмножестве.

        kind обязателен для кэша: иначе результат поиска по улицам вернулся бы
        для жилмассивов («Абай» находился бы как улица, даже когда ищем ЖК).
        """
        qk = norm_key(query).lower()
        cache_key = f"fz:{kind}:{qk}"
        if cache_key in self._fuzzy_cache:
            return self._fuzzy_cache[cache_key]

        prefix = _prefix(qk)
        if prefix in index:
            candidates = index[prefix]
        else:
            candidates = full_list if full_list is not None else [n for v in index.values() for n in v]

        result = fuzzy_find(query, candidates)

        if len(self._fuzzy_cache) < self._FUZZY_CACHE_SIZE:
            self._fuzzy_cache[cache_key] = result
        return result

    # === точный поиск ===
    def find_province(self, key: str) -> Optional[Any]:
        for k in _keys(key):
            row = self._first("SELECT name, code FROM provinces WHERE key=? LIMIT 1", (k,))
            if row:
                return row
        return None

    def _strict_city(self, key: str) -> Optional[Any]:
        for k in _keys(key):
            row = self._first(
                "SELECT name, name_kk, province, code, kind, rank, is_city_of_republic "
                "FROM cities WHERE key=? ORDER BY rank ASC LIMIT 1", (k,))
            if row:
                return row
        for k in _keys(key):
            if k in self._aliases and self._aliases[k].get("type") == "city":
                info = self._aliases[k]
                n = info.get("canonical", key)
                return AliasRow({"name": n, "name_kk": n, "province": info.get("province", ""),
                                 "code": None, "kind": "город", "rank": 0, "is_city_of_republic": 0})
        return None

    def find_city(self, key: str, strict: bool = False) -> Optional[Any]:
        row = self._strict_city(key)
        if row:
            return row
        if not strict and self._all_cities:
            for variant in _keys(key):
                best, score = self._fuzzy_lookup(variant, self._city_index, self._all_cities, "city")
                if best:
                    return self._strict_city(best)
        return None

    def find_district(self, key: str, city: Optional[str] = None) -> Optional[Any]:
        for k in _keys(key):
            if city:
                row = self._first(
                    "SELECT name, city, province, kind, code FROM districts "
                    "WHERE key=? AND (city=? OR city IS NULL) ORDER BY (city=?) DESC LIMIT 1", (k, city, city))
            else:
                row = self._first("SELECT name, city, province, kind, code FROM districts WHERE key=? LIMIT 1", (k,))
            if row:
                return row
        return None

    _VOWELS = set("аяыиеуюоь")

    def _district_hint(self, key: str, city: Optional[str]) -> Optional[str]:
        """Район по близкой записи той же улицы.

        В OSM одна и та же улица лежит несколькими строками: «улица Абая»,
        «Абай», «Абая ул.». Район посчитан не у всех, поэтому ищем соседнюю
        запись с тем же началом названия, у которой район есть.
        """
        if not city:
            return None
        base = norm_key(key).split()[0] if norm_key(key) else ""
        if len(base) < 4:
            return None
        if len(base) >= 4 and base[-1] in self._VOWELS:
            base = base[:-1]
        row = self._first(
            "SELECT district FROM streets WHERE city=? AND district IS NOT NULL "
            "AND key LIKE ? AND LENGTH(key) <= ? ORDER BY LENGTH(key) ASC LIMIT 1",
            (city, base + "%", len(base) + 3))
        return row["district"] if row else None

    def _prefix_street(self, key: str, city: Optional[str]) -> Optional[Any]:
        """Совпадение по началу слова: «улица Абая» -> «Абай даңғылы».

        Только для ОДНОСЛОВНЫХ запросов: иначе «толе батыра» цеплялось за
        «Толе би» в Алматы (оба начинаются на «толе»), и город определялся
        неверно — Пришахтинск уезжал в Алматы.
        """
        for cand in _keys(key):
            if len(cand.split()) != 1:
                continue
            head = cand
            if len(head) < 4 or head.isdigit():
                continue
            if city:
                row = self._first(
                    "SELECT name, street_type, city, district, source FROM streets "
                    "WHERE key LIKE ? AND city=? ORDER BY (district IS NULL) ASC, cnt DESC, LENGTH(key) ASC LIMIT 1",
                    (head + "%", city))
            else:
                rows = self._query(
                    "SELECT name, street_type, city, district, source FROM streets "
                    "WHERE key LIKE ? ORDER BY (district IS NULL) ASC, cnt DESC, LENGTH(key) ASC "
                    "LIMIT 100", (head + "%",))
                # без города берём только однозначный вариант: «Абая» тянет за
                # собой «Абая тупик» из Тараза, а это уже выдумка
                cities = {r["city"] for r in rows if r["city"]}
                row = self._best_street_row(rows) if len(cities) == 1 else None
            if row:
                return row
        return None

    #: слова, которые не могут быть «именем» улицы при поиске по слову
    _STOP_WORDS = {
        "улица", "проспект", "переулок", "бульвар", "площадь", "шоссе", "тупик",
        "микрорайон", "квартал", "аллея", "набережная", "тракт", "разъезд", "станция",
        "кошеси", "коше", "данғылы", "данғыл", "алаңы", "алаң", "шағын", "ауданы",
    }

    def _token_street(self, key: str, city: Optional[str]) -> Optional[Any]:
        """Улица по слову внутри названия.

        В OSM улица может быть записана с именем: «Саттар Ерубаев көшесі»,
        а человек пишет «улица Ерубаева». Точного и префиксного совпадения нет,
        но слово «ерубаев» внутри названия есть.
        """
        for cand in _keys(key):
            for word in cand.split():
                if len(word) < 5 or word.isdigit() or word in self._STOP_WORDS:
                    continue
                if city:
                    row = self._first(
                        "SELECT name, street_type, city, district, source FROM streets "
                        "WHERE key LIKE ? AND city=? ORDER BY LENGTH(key) ASC LIMIT 1",
                        (f"%{word}%", city))
                else:
                    row = self._first(
                        "SELECT name, street_type, city, district, source FROM streets "
                        "WHERE key LIKE ? ORDER BY LENGTH(key) ASC LIMIT 1", (f"%{word}%",))
                if row:
                    return row
        return None

    def _best_street_row(self, rows: List[Any]) -> Optional[Any]:
        """Выбрать самую правдоподобную строку улицы, если город не указан.

        «Абая» есть в Алматы (проспект), в Таразе (тупик) и ещё в десятке мест.
        Без города нельзя угадать точно, но случайный «тупик в Таразе» — худший
        вариант. Поэтому сначала идёт город, про который справочник знает больше
        улиц (фактически — размер города), а при равенстве — запись с районом.
        """
        if not rows:
            return None
        if len(rows) == 1:
            return rows[0]

        # порядок крупных городов: при равных данных выигрывает более вероятный
        priority = {name: i for i, name in enumerate((
            "Алматы", "Астана", "Шымкент", "Караганда", "Актобе", "Тараз",
            "Павлодар", "Усть-Каменогорск", "Семей", "Атырау", "Костанай",
            "Кызылорда", "Уральск", "Петропавловск", "Актау", "Темиртау",
            "Туркестан", "Кокшетау", "Талдыкорган", "Экибастуз", "Балхаш",
            "Жезказган", "Конаев", "Рудный", "Кентау", "Сатпаев", "Талгар",
            "Каскелен",
        ))}

        def weight(item):
            row = item[1]
            city = row["city"] or ""
            return (
                -priority.get(city, len(priority)),
                1 if row["district"] else 0,
                self._city_weight.get(city, 0),
            )

        return max(enumerate(rows), key=weight)[1]

    def street_exists(self, key: str) -> bool:
        """Есть ли такая улица вообще (в любом городе).

        Нужно, чтобы не принять название улицы за город: «Туран 55/6» —
        это улица Туран, а не посёлок Туран.
        """
        for k in _keys(key):
            if self._first("SELECT 1 FROM streets WHERE key=? LIMIT 1", (k,)):
                return True
        return False

    def find_street(self, key: str, city: Optional[str] = None) -> Optional[Any]:
        # 1. точное совпадение (включая транслит и падежи)
        for k in _keys(key):
            if city:
                # город известен — ищем ТОЛЬКО в нём: улица из другого города
                # не должна подменять район и тип
                row = self._first(
                    "SELECT name, street_type, city, district, source FROM streets "
                    "WHERE key=? AND city=? ORDER BY (district IS NULL) ASC, cnt DESC LIMIT 1", (k, city))
                if row:
                    return row
            else:
                rows = self._query(
                    "SELECT name, street_type, city, district, source FROM streets "
                    "WHERE key=?", (k,))
                # Город в строке не назван. Восстанавливаем его только когда
                # улица есть ровно в одном городе справочника: «Жуалы» — только
                # в Алматы, это надёжно. «Абая», «Достык» есть в десятке городов —
                # гадать нельзя, иначе курьер поедет в Караганду вместо Алматы.
                cities = {r["city"] for r in rows if r["city"]}
                if len(cities) == 1:
                    row = self._best_street_row(rows)
                elif cities:
                    row = None
                else:
                    row = self._best_street_row(rows)
                if row and row["district"] is None:
                    # Название без типа может совпасть с «голой» записью из города,
                    # где район не восстановлен, хотя в другом городе есть полная
                    # «улица Курильская» с районом. Такой вариант полезнее.
                    alt = self._first(
                        "SELECT name, street_type, city, district, source FROM streets "
                        "WHERE key IN ('улица '||?, 'проспект '||?, 'мкр '||?, 'микрорайон '||?, "
                        "'переулок '||?, 'бульвар '||?, 'шоссе '||?, 'площадь '||?, 'квартал '||?) "
                        "AND district IS NOT NULL ORDER BY cnt DESC LIMIT 1", (k,) * 9)
                    if alt:
                        row = alt
                if row:
                    return row

        # 2. начало слова
        row = self._prefix_street(key, city)
        if row:
            return row

        # 2.5 слово внутри названия («Ерубаева» -> «Саттар Ерубаев»).
        # Только когда город известен: без города поиск по слову цепляет
        # одноимённую улицу из чужого города («Курильская» -> Караганда).
        if city:
            row = self._token_street(key, city)
            if row:
                return row

        # 3. алиасы
        for nk in _keys(key):
            if nk in self._aliases and self._aliases[nk].get("type") == "street":
                info = self._aliases[nk]
                return AliasRow({"name": info.get("canonical", key), "street_type": info.get("street_type", "улица"),
                                 "city": city or info.get("city", ""), "district": info.get("district"),
                                 "source": "alias"})

        # 4. fuzzy — строго в пределах города, если он известен
        if city:
            index = self._city_names(city, "streets")
            if not index:
                return None
            best, score = self._fuzzy_lookup(key, index, kind=f"street:{city}")
            if not best:
                return None
            return self._first(
                "SELECT name, street_type, city, district, source FROM streets "
                "WHERE key=? AND city=? LIMIT 1", (norm_key(best), city))

        if self._all_streets:
            best, score = self._fuzzy_lookup(key, self._street_index, self._all_streets, "street")
            if best:
                rows = self._query(
                    "SELECT name, street_type, city, district, source FROM streets "
                    "WHERE key=?", (norm_key(best),))
                # и здесь без города — только однозначный вариант
                cities = {r["city"] for r in rows if r["city"]}
                if len(cities) == 1:
                    return self._best_street_row(rows)
        return None

    def find_living_area(self, key: str, city: Optional[str] = None) -> Optional[Any]:
        for k in _keys(key):
            if city:
                row = self._first(
                    "SELECT name, city, district, kind, source, rank FROM living_areas "
                    "WHERE key=? AND city=? ORDER BY rank ASC LIMIT 1", (k, city))
                if row:
                    return row
            else:
                row = self._first(
                    "SELECT name, city, district, kind, source, rank FROM living_areas "
                    "WHERE key=? ORDER BY rank ASC LIMIT 1", (k,))
                if row:
                    return row

        # начало слова — «Аксай 3а» находится по «аксай»
        # (только односложный запрос, см. комментарий в _prefix_street)
        for cand in _keys(key):
            if len(cand.split()) != 1:
                continue
            head = cand
            if len(head) < 4 or head.isdigit():
                continue
            if city:
                row = self._first(
                    "SELECT name, city, district, kind, source, rank FROM living_areas "
                    "WHERE key LIKE ? AND city=? ORDER BY rank ASC, LENGTH(key) ASC LIMIT 1",
                    (head + "%", city))
            else:
                row = self._first(
                    "SELECT name, city, district, kind, source, rank FROM living_areas "
                    "WHERE key LIKE ? ORDER BY rank ASC, LENGTH(key) ASC LIMIT 1", (head + "%",))
            if row:
                return row

        for nk in _keys(key):
            if nk in self._aliases and self._aliases[nk].get("type") == "living_area":
                info = self._aliases[nk]
                return AliasRow({"name": info.get("canonical", key), "city": city or info.get("city", ""),
                                 "district": info.get("district"), "kind": "ЖК", "source": "alias"})

        if city:
            index = self._city_names(city, "living_areas")
            if not index:
                return None
            best, score = self._fuzzy_lookup(key, index, kind=f"living:{city}")
            if not best:
                return None
            return self._first(
                "SELECT name, city, district, kind, source, rank FROM living_areas "
                "WHERE key=? AND city=? LIMIT 1", (norm_key(best), city))

        if self._all_living:
            best, score = self._fuzzy_lookup(key, self._living_index, self._all_living, "living")
            if best:
                return self._first(
                    "SELECT name, city, district, kind, source, rank FROM living_areas "
                    "WHERE key=? LIMIT 1", (norm_key(best),))
        return None

    _KZ_LETTERS = set("әғқңөұүһі")

    #: ТЗ требует область «в прямом порядке»: «Актюбинская область», а не
    #: «область Актобе» и не казахское «Ақтөбе облысы». КАТО отдаёт часть
    #: регионов в обратном порядке и по-казахски — приводим к русской форме.
    PROVINCE_DISPLAY = {
        "акмолинская область": "Акмолинская область",
        "акмола область": "Акмолинская область",
        "акмола облысы": "Акмолинская область",
        "актюбинская область": "Актюбинская область",
        "актобе область": "Актюбинская область",
        "актобе облысы": "Актюбинская область",
        "алматинская область": "Алматинская область",
        "алматы облысы": "Алматинская область",
        "атырауская область": "Атырауская область",
        "атырау облысы": "Атырауская область",
        "восточно-казахстанская область": "Восточно-Казахстанская область",
        "шыгыс казахстан облысы": "Восточно-Казахстанская область",
        "жамбылская область": "Жамбылская область",
        "жамбыл облысы": "Жамбылская область",
        "жетысуская область": "Жетысуская область",
        "область жетысу": "Жетысуская область",
        "область жетису": "Жетысуская область",
        "жетысу облысы": "Жетысуская область",
        "жетису облысы": "Жетысуская область",
        "западно-казахстанская область": "Западно-Казахстанская область",
        "батыс казахстан облысы": "Западно-Казахстанская область",
        "карагандинская область": "Карагандинская область",
        "караганды облысы": "Карагандинская область",
        "костанайская область": "Костанайская область",
        "костанай облысы": "Костанайская область",
        "кызылординская область": "Кызылординская область",
        "кызылорда облысы": "Кызылординская область",
        "мангистауская область": "Мангистауская область",
        "мангыстау облысы": "Мангистауская область",
        "павлодарская область": "Павлодарская область",
        "павлодар облысы": "Павлодарская область",
        "северо-казахстанская область": "Северо-Казахстанская область",
        "солтустик казахстан облысы": "Северо-Казахстанская область",
        "туркестанская область": "Туркестанская область",
        "туркестан облысы": "Туркестанская область",
        "улытауская область": "Улытауская область",
        "область улытау": "Улытауская область",
        "улытау облысы": "Улытауская область",
        "абайская область": "Абайская область",
        "абай облысы": "Абайская область",
        "алматы": "Алматы",
        "астана": "Астана",
        "шымкент": "Шымкент",
    }

    def province_display(self, name: str) -> str:
        """Привести область к русской форме «<X>ская область» (требование ТЗ)."""
        if not name:
            return name
        key = norm_key(name)
        hit = self.PROVINCE_DISPLAY.get(key)
        if hit:
            return hit
        # «область Ұлытау» → ищем по хвосту без слова «область»
        tail = re.sub(r"^(?:область|облысы)\s+|\s+облысы$", "", name, flags=re.IGNORECASE)
        tail = tail.strip()
        return self.PROVINCE_DISPLAY.get(norm_key(tail), name)

    def city_display(self, name: str) -> str:
        """Русское написание города для ответа.

        В КАТО часть названий записана по-казахски («Қонаев»), а человек и жюри
        ждут «Конаев». Если в справочнике есть то же название в русской графике —
        возвращаем его.
        """
        if not name or not (set(name.lower()) & self._KZ_LETTERS):
            return name
        key = norm_key(name)
        for alt in self._all_cities:
            if norm_key(alt) == key and not (set(alt.lower()) & self._KZ_LETTERS):
                return alt
        # Русского варианта в справочнике нет — переводим буквы сами.
        table = str.maketrans({
            "ә": "а", "ғ": "г", "қ": "к", "ң": "н", "ө": "о", "ұ": "у", "ү": "у",
            "һ": "х", "і": "и",
            "Ә": "А", "Ғ": "Г", "Қ": "К", "Ң": "Н", "Ө": "О", "Ұ": "У", "Ү": "У",
            "Һ": "Х", "І": "И",
        })
        return name.translate(table)

    def city_by_district(self, key: str) -> Optional[str]:
        for k in _keys(key):
            row = self._first("SELECT city FROM districts WHERE key=? AND city IS NOT NULL LIMIT 1", (k,))
            if row:
                return row["city"]
        return None

    def describe(self) -> str:
        if not self.available:
            return "справочник не подключён"
        parts = [f"{k}: {v}" for k, v in self.stats.items()]
        if self._aliases:
            parts.append(f"aliases: {len(self._aliases)}")
        if self._all_cities:
            parts.append(f"fuzzy_cities: {len(self._all_cities)}")
        parts.append(f"cache: {len(self._fuzzy_cache)}")
        return ", ".join(parts)


def _prefix(key: str) -> str:
    """Ключ индекса: первые 2 символа нормализованного названия."""
    k = (key or "").lower()
    return k[:2] if len(k) >= 2 else k[:1]


def _keys(value: str) -> List[str]:
    """Все варианты ключа: точный, падежный и транслит латиницы."""
    return search_keys(value)


_GZ: Optional[Gazetteer] = None


def get_gazetteer(path: str = DEFAULT_PATH) -> Gazetteer:
    global _GZ
    if _GZ is None or (path != DEFAULT_PATH and _GZ.path != path):
        _GZ = Gazetteer(path)
    return _GZ
