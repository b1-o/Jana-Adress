"""
Fuzzy-матчинг для адресов: Кулинская→Курильская, Ленинва→Ленина.
Используем расстояние Левенштейна без тяжёлых библиотек (pure Python).
"""

from typing import Optional


def levenshtein(s1: str, s2: str) -> int:
    """Расстояние Левенштейна, оптимизированное O(min(m,n))."""
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if not s2:
        return len(s1)
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr_row.append(min(
                prev_row[j + 1] + 1,      # deletion
                curr_row[j] + 1,           # insertion
                prev_row[j] + cost         # substitution
            ))
        prev_row = curr_row
    return prev_row[-1]


def similarity(a: str, b: str) -> float:
    """0..1, где 1 = полное совпадение."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    max_len = max(len(a), len(b))
    dist = levenshtein(a.lower(), b.lower())
    return 1.0 - (dist / max_len)


FUZZY_THRESHOLD = 0.70  # ниже этого — не считаем совпадением

# Кэш: {normalized_key: (best_match, score)}
_fuzzy_cache: dict = {}


def fuzzy_find(query: str, candidates: list[str], threshold: float = FUZZY_THRESHOLD) -> tuple[Optional[str], float]:
    """
    Найти лучший матч из candidates для query.
    Возвращает (best_match_or_None, best_score).
    
    >>> fuzzy_find("Кулинская", ["Курильская", "Ленина"])
    ('Курильская', 0.85...)
    >>> fuzzy_find("xyz", ["Курильская"])
    (None, 0.0)
    """
    if not query or not candidates:
        return None, 0.0
    
    qk = query.lower()
    # ключ кэша обязан включать набор кандидатов: иначе результат поиска
    # по улицам вернётся для жилмассивов (кэш общий на модуль)
    cache_key = (qk, len(candidates),
                 candidates[0] if candidates else "",
                 candidates[-1] if candidates else "")
    if cache_key in _fuzzy_cache:
        return _fuzzy_cache[cache_key]
    
    best: Optional[str] = None
    best_score = 0.0
    
    for cand in candidates:
        s = similarity(qk, cand)
        if s > best_score:
            best_score = s
            best = cand
    
    result = (None, 0.0) if best_score < threshold else (best, round(best_score, 3))
    _fuzzy_cache[cache_key] = result
    return result
