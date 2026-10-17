"""Тесты fuzzy-матчинга (расстояние Левенштейна)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.fuzzy import levenshtein, similarity, fuzzy_find


def test_levenshtein_identity():
    assert levenshtein("Курильская", "Курильская") == 0


def test_levenshtein_one_char():
    assert levenshtein("тест", "тес") == 1


def test_similarity_high():
    s = similarity("Кулинская", "Курильская")
    assert 0.65 <= s <= 0.85


def test_similarity_low():
    assert similarity("Туран", "Туркестанская") < 0.5


def test_fuzzy_find_match():
    best, score = fuzzy_find("Кулинская", ["Курильская", "Ленина", "Назарбаева"])
    assert best == "Курильская"
    assert score >= 0.70


def test_fuzzy_find_no_match():
    best, score = fuzzy_find("xyz123", ["Курильская", "Ленина"])
    assert best is None
    assert score == 0.0


def test_fuzzy_empty():
    best, score = fuzzy_find("", ["test"])
    assert best is None
