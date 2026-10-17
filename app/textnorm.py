"""Нормализация строк адресов RU/KZ.

Что делаем:
  * склеиваем невидимые служебные символы (ZWSP, BOM, LRM/RLM, soft hyphen);
  * неразрывные пробелы -> обычные, любые тире -> дефис;
  * NFKC (полноширинные цифры/буквы -> обычные);
  * ключ сопоставления: нижний регистр, казахские буквы -> русские аналоги,
    схлопывание пунктуации и пробелов.

Это ровно те пункты из кейса, которые ломают наивные парсеры
(«Невидимые служебные символы внутри строк», «Лишние пробелы», «Ул .Курильская»).
"""
from __future__ import annotations

import re
import unicodedata

from .lang import has_latin, strip_admin_en, translit_latin

_INVISIBLE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff\u00ad]")
_DASHES = re.compile(r"[\u2010-\u2015\u2212\u2043]")
_SPACES = re.compile(r"[ \t\r\n]+")

# казахские буквы -> близкие русские (для нечёткого сопоставления справочника)
_KK2RU = str.maketrans({
    "ә": "а", "ғ": "г", "қ": "к", "ң": "н", "ө": "о", "ұ": "у", "ү": "у",
    "һ": "х", "і": "и", "Ә": "А", "Ғ": "Г", "Қ": "К", "Ң": "Н", "Ө": "О",
    "Ұ": "У", "Ү": "У", "Һ": "Х", "І": "И", "ё": "е", "Ё": "Е", "э": "е", "Э": "Е",
})

_PUNCT = re.compile(r"[^0-9a-zа-я]+")


def normalize(raw: str) -> str:
    """Привести строку к «чистому» виду, сохранив исходные написания слов."""
    if not raw:
        return ""
    s = unicodedata.normalize("NFKC", str(raw))
    s = s.replace("\u00a0", " ").replace("\u202f", " ")
    s = _INVISIBLE.sub("", s)
    s = _DASHES.sub("-", s)
    for a, b in (("«", '"'), ("»", '"'), ("“", '"'), ("”", '"'), ("„", '"'), ("ʼ", "'")):
        s = s.replace(a, b)
    s = _SPACES.sub(" ", s)
    return s.strip(" ,;.")


def norm_key(value: str) -> str:
    """Ключ для сопоставления со справочником: 'Мкр. Ақсай-3а' -> 'мкр аксай 3а'."""
    s = normalize(value).lower().translate(_KK2RU)
    s = _PUNCT.sub(" ", s)
    return _SPACES.sub(" ", s).strip()


#: «хвосты» русских падежей, которые встречаются в адресных строках
_CASE_TAILS = (
    "ого", "его", "ому", "ему", "ыми", "ими", "ой", "ый", "ий", "ая", "яя", "ое", "ее",
    "ам", "ям", "ах", "ях", "ов", "ев", "ым", "им", "ую", "юю", "ии", "ия", "ье", "ья",
    "а", "я", "ы", "и", "е", "у", "ю", "о", "ь",
)


def stem_key(value: str) -> str:
    """Усечённый ключ: 'курильская' -> 'курильск', 'абая' -> 'аба'.

    Нужен только как fallback, когда точного совпадения со справочником нет
    (в адресах пишут «улица Абая», а в OSM — «проспект Абая» / «Абай даңғылы»).
    """
    key = norm_key(value)
    out = []
    for word in key.split(" "):
        if len(word) > 4 and not word.isdigit():
            for tail in _CASE_TAILS:
                if word.endswith(tail) and len(word) - len(tail) >= 4:
                    word = word[: len(word) - len(tail)]
                    break
        out.append(word)
    return " ".join(out)


def split_segments(text: str) -> list[str]:
    """Разбить адрес на смысловые куски.

    Слэш между цифрами — часть номера дома («55/6», «1/2»), слэш между словами —
    разделитель двуязычной склейки («город Алматы/Алматы қаласы»).
    """
    text = re.sub(r"(?<=\d)\s*/\s*(?=\d)", "/", text)          # 55 / 6 -> 55/6
    text = re.sub(r"(?<=[^\d\s])\s*/\s*(?=[^\d\s])", " | ", text)  # Алматы/Алматы қаласы -> два сегмента
    parts = re.split(r"\s*[,;|]\s*", text)
    return [p.strip() for p in parts if p and p.strip()]


def lookup_keys(value: str) -> list[str]:
    """Ключи для поиска в справочнике: обычный + транслит латиницы.

    Справочник хранит ключи в русской графике ('абай дангылы'), а человек
    может написать «Abai street» или «Абай көшесі». Поэтому для строки с
    латиницей пробуем ещё и кириллический вариант.

    >>> lookup_keys("Abai")
    ['abai', 'абай']
    >>> lookup_keys("Almaty city")
    ['almaty city', 'алматы']
    """
    base = norm_key(value)
    keys: list[str] = [base]
    if has_latin(base):
        src = strip_admin_en(normalize(value))
        tr = norm_key(translit_latin(src))
        if tr and tr not in keys:
            keys.append(tr)
    return keys


def search_keys(value: str) -> list[str]:
    """Расширенный набор ключей: точный, транслит и усечённый (падежи).

    Используется справочником, когда точного совпадения не нашлось.
    """
    out: list[str] = []
    for k in lookup_keys(value):
        for variant in (k, stem_key(k)):
            if variant and variant not in out:
                out.append(variant)
    return out


def collapse_number(num: str) -> str:
    """'55 / 6' -> '55/6', '12 а' -> '12а'. Дефис в номере дома сохраняем («33-1» ≠ «33/1»)."""
    n = normalize(num).lower().replace(" ", "")
    n = re.sub(r"^0+(\d)", r"\1", n)          # 007 -> 7
    return n
