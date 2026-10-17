"""Мультиязычные словари и транслитерация для разбора адресов.

Зачем нужен отдельный модуль:
  * человек пишет адрес на русском, казахском или английском —
    «улица Абая», «Абай көшесі», «Abai street» — и все три варианта
    должны находить одну и ту же улицу в справочнике;
  * справочник хранит ключи в русской графике ('абай дангылы'),
    поэтому латиница и казахские буквы приводятся к тому же виду.

Что внутри:
  * ``translit_latin`` — латиница -> кириллица (Almaty -> алматы, Abai -> абай);
  * ``STREET_TYPES_EN`` / ``STREET_TYPES_KZ`` — типы улиц на трёх языках;
  * ``normalize_type_phrases`` — склейка составных типов («шағын ауданы» -> «мкр»);
  * ``ADMIN_EN`` — служебные слова (city, street, district …).
"""
from __future__ import annotations

import re

# ─────────────────────────────────────────────────────────────────────────────
# 1. Латиница -> кириллица
# ─────────────────────────────────────────────────────────────────────────────

#: многобуквенные сочетания — проверяются раньше одиночных
_MULTI = (
    ("shch", "щ"), ("sch", "щ"),
    ("zh", "ж"), ("kh", "х"), ("ts", "ц"), ("ch", "ч"), ("sh", "ш"),
    ("ya", "я"), ("yu", "ю"), ("yo", "ё"), ("ye", "е"),
    # казахские дифтонги на конце/внутри: Abai -> абай, Seifullin -> сейфуллин
    ("ai", "ай"), ("ei", "ей"), ("oi", "ой"), ("ui", "уй"),
)

_SINGLE = {
    "a": "а", "b": "б", "v": "в", "w": "в", "g": "г", "d": "д", "e": "е",
    "z": "з", "i": "и", "j": "дж", "k": "к", "c": "к", "l": "л", "m": "м",
    "n": "н", "o": "о", "p": "п", "q": "к", "r": "р", "s": "с", "t": "т",
    "u": "у", "f": "ф", "h": "х", "x": "кс",
}

_VOWELS_CYR = "аеиоуыэюяё"


def has_latin(text: str) -> bool:
    """Есть ли в строке латинские буквы."""
    return bool(re.search(r"[a-z]", text or "", re.IGNORECASE))


def translit_latin(text: str) -> str:
    """Латиница -> кириллица с учётом контекста.

    >>> translit_latin("Almaty")
    'алматы'
    >>> translit_latin("Abai")
    'абай'
    >>> translit_latin("Shymkent")
    'шымкент'
    >>> translit_latin("Kabanbay batyr")
    'кабанбай батыр'
    """
    if not text:
        return ""
    s = text.lower()
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        matched = False
        for src, dst in _MULTI:
            if s.startswith(src, i):
                out.append(dst)
                i += len(src)
                matched = True
                break
        if matched:
            continue

        ch = s[i]
        if ch == "y":
            # «y» после гласной — й (Abay -> абай), после согласной — ы (Almaty -> алматы)
            prev = out[-1][-1] if out else ""
            out.append("й" if prev in _VOWELS_CYR else "ы")
        elif ch in _SINGLE:
            out.append(_SINGLE[ch])
        else:
            out.append(ch)
        i += 1
    return "".join(out)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Типы улиц на английском и казахском
# ─────────────────────────────────────────────────────────────────────────────

#: английские написания -> канонический русский тип
STREET_TYPES_EN: dict[str, str] = {
    "street": "улица", "st": "улица", "str": "улица", "ul": "улица", "ulitsa": "улица",
    "avenue": "проспект", "ave": "проспект", "av": "проспект", "avn": "проспект",
    "prospect": "проспект", "prospekt": "проспект", "pr": "проспект", "prt": "проспект",
    "boulevard": "бульвар", "blvd": "бульвар", "bulvar": "бульвар",
    "lane": "переулок", "ln": "переулок", "pereulok": "переулок", "per": "переулок",
    "square": "площадь", "sq": "площадь", "pl": "площадь", "ploshchad": "площадь",
    "microdistrict": "микрорайон", "micro": "микрорайон", "mikrorayon": "микрорайон",
    "mkr": "микрорайон", "mkrn": "микрорайон", "md": "микрорайон",
    "block": "квартал", "quarter": "квартал", "kvartal": "квартал", "qtr": "квартал",
    "highway": "шоссе", "hwy": "шоссе", "road": "шоссе", "rd": "шоссе",
    "alley": "аллея", "embankment": "набережная", "nab": "набережная",
    "deadend": "тупик", "tupik": "тупик", "station": "станция",
}

#: казахские написания -> канонический русский тип
#: (часть уже есть в parser.STREET_TYPES, здесь — то, чего там не хватает)
STREET_TYPES_KZ: dict[str, str] = {
    "шағын ауданы": "микрорайон", "шағын аудан": "микрорайон",
    "ықшамаудан": "микрорайон", "ықшам аудан": "микрорайон", "ыкшамаудан": "микрорайон",
    "көшесі": "улица", "көше": "улица", "кошеси": "улица", "коше": "улица",
    "к-сі": "улица", "к-сы": "улица", "көш.": "улица", "кош.": "улица",
    "даңғылы": "проспект", "даңғыл": "проспект", "данғылы": "проспект", "данғыл": "проспект",
    "даңғ.": "проспект", "данғ.": "проспект",
    "алаңы": "площадь", "алаң": "площадь", "алан": "площадь",
    "тұйық": "тупик", "туйық": "тупик", "туйык": "тупик",
    "бульвары": "бульвар", "тас жол": "шоссе", "тас жолы": "шоссе",
    "станциясы": "станция", "разъезді": "разъезд",
}

#: составные типы: длинные фразы заменяем одним токеном до разбора
_COMPOUND = {
    "шағын ауданы": "мкр", "шағын аудан": "мкр",
    "ықшам аудан": "мкр", "ықшамаудан": "мкр", "ыкшамаудан": "мкр",
    "тас жолы": "шоссе", "тас жол": "шоссе",
    "micro district": "мкр", "microdistrict": "мкр",
}

_COMPOUND_RE = re.compile(
    "|".join(r"\s+".join(map(re.escape, k.split())) for k in sorted(_COMPOUND, key=len, reverse=True)),
    re.IGNORECASE,
)


def normalize_type_phrases(text: str) -> str:
    """Склеить составные типы в один токен, чтобы токенизатор их узнал.

    >>> normalize_type_phrases("Нурсити шағын ауданы 11")
    'Нурсити мкр 11'
    """
    if not text:
        return text
    return _COMPOUND_RE.sub(lambda m: _COMPOUND[re.sub(r"\s+", " ", m.group(0).lower())], text)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Служебные слова админ-уровней на английском и казахском
# ─────────────────────────────────────────────────────────────────────────────

#: город
CITY_EN = ("city", "town", "township")
#: район
DISTRICT_EN = ("district", "area", "rayon", "raion")
#: область
REGION_EN = ("region", "province", "oblast", "oblasti", "state")
#: поселение
VILLAGE_EN = ("village", "settlement", "selo", "aul", "auls")

#: квартира
APT_EN = ("flat", "apt", "apartment", "app", "unit", "suite")
#: подъезд
ENTRANCE_EN = ("entrance", "porch", "entry", "stairwell", "podyezd")
#: этаж
FLOOR_EN = ("floor", "fl", "storey", "story", "level")
#: дом
HOUSE_EN = ("house", "bldg", "building", "blk")


_ADMIN_EN_RE = re.compile(
    r"\b(?:" + "|".join(sorted(set(
        CITY_EN + DISTRICT_EN + REGION_EN + VILLAGE_EN + tuple(STREET_TYPES_EN)
    ), key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def strip_admin_en(text: str) -> str:
    """Убрать английские служебные слова перед транслитерацией.

    «Almaty city» -> «Almaty»: иначе «city» превратится в «киты».
    """
    if not text:
        return text
    return re.sub(r"\s+", " ", _ADMIN_EN_RE.sub(" ", text)).strip()


def alias_token(token: str) -> str | None:
    """Канонический тип улицы по английскому/казахскому токену."""
    t = (token or "").strip(".,;:").lower()
    if not t:
        return None
    return STREET_TYPES_EN.get(t) or STREET_TYPES_KZ.get(t)


def all_type_tokens() -> dict[str, str]:
    """Полный словарь токен -> канонический тип (EN + KZ)."""
    merged: dict[str, str] = {}
    merged.update(STREET_TYPES_KZ)
    merged.update(STREET_TYPES_EN)
    return merged
