"""
Оценка уверенности разбора адреса.
Возвращает score 0.0–1.0 + предупреждения для UI.
"""

import re
from typing import Dict, Optional, List


CORE_FIELDS = ['city', 'street_name', 'house']
OPTIONAL_FIELDS = ['province', 'district', 'living_area', 'apartment', 'entrance', 'floor']

VALID_HOUSE = re.compile(r'^\d+[а-яА-Я]?(/\d+)?$', re.UNICODE)
VALID_APT = re.compile(r'^\d+[а-яА-Я]?$', re.UNICODE)
VALID_FLOOR = re.compile(r'^\d{1,3}$')
VALID_ENTRANCE = re.compile(r'^\d{1,2}$')

GARBAGE_WORDS = [
    'магазин', 'тц', 'бц', 'аптека', 'школа', 'детсад',
    'остановка', 'ориентир', 'рядом', 'напротив', 'возле',
    'qazpost', 'береке', 'солнечный', 'марьям', 'азык',
]


def _is_garbage(value: str) -> bool:
    if not value:
        return False
    lower = value.lower()
    return any(w in lower for w in GARBAGE_WORDS)


def _field_score(field: str, value: Optional[str]) -> float:
    if not value or not value.strip():
        return 0.0
    v = value.strip()
    if _is_garbage(v):
        return 0.3
    if field == 'house':
        return 1.0 if VALID_HOUSE.match(v) else 0.5
    if field == 'apartment':
        return 1.0 if VALID_APT.match(v) else 0.5
    if field == 'floor':
        return 1.0 if VALID_FLOOR.match(v) else 0.5
    if field == 'entrance':
        return 1.0 if VALID_ENTRANCE.match(v) else 0.5
    if len(v) < 2:
        return 0.3
    if re.search(r'\d', v) and field in ('city', 'province', 'district'):
        return 0.4
    return 0.9


def compute_confidence(parsed: Dict[str, Optional[str]],
                       sources: Optional[Dict[str, str]] = None) -> Dict:
    """Оценка уверенности.

    ``sources`` — откуда взято поле (см. ``_sources`` в парсере). Если улица
    или жилмассив подтвердились справочником, это доказательство: такая
    строка надёжнее, чем «красиво разобранная, но нигде не найденная».
    """
    sources = sources or {}
    details = {}
    warnings: List[str] = []

    filled = [f for f in CORE_FIELDS + OPTIONAL_FIELDS if parsed.get(f)]
    verified_street = bool(sources.get("street_verified"))
    verified_living = bool(sources.get("living_verified"))

    for field in filled:
        s = _field_score(field, parsed.get(field))
        if field == "street_name" and s >= 0.9:
            # подтверждена справочником — почти наверняка; не подтверждена —
            # возможно, опечатка или несуществующая улица
            s = 0.98 if verified_street else 0.75
            if not verified_street:
                warnings.append(f"Улица не найдена в справочнике: '{parsed.get(field)}'")
        if field == "living_area" and s >= 0.9:
            s = 0.95 if verified_living else 0.75
        details[field] = round(s, 2)
        if s < 0.5:
            warnings.append(f"Слабое поле '{field}': '{parsed.get(field)}'")
        if _is_garbage(parsed.get(field) or ''):
            warnings.append(f"Ориентир в поле '{field}': '{parsed.get(field)}'")

    if not filled:
        return {"score": 0.0, "details": {}, "warnings": ["Ничего не распознано"]}

    quality = sum(details.values()) / len(filled)
    completeness = min(len(filled) / 4, 1.0)
    overall = quality * 0.7 + completeness * 0.3

    # ни улицы, ни жилмассива, подтверждённых справочником — потолок 0.8
    if not verified_street and not verified_living and parsed.get("street_name"):
        overall = min(overall, 0.8)

    return {
        "score": round(overall, 2),
        "details": details,
        "warnings": warnings,
    }
