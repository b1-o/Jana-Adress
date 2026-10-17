import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.preprocessor import preprocess_address
from app.confidence import compute_confidence


def test_invisible_chars():
    assert preprocess_address("ул.\u200bКурильская") == "ул. Курильская"
    assert preprocess_address("\ufeffул. Ленина 1") == "ул. Ленина 1"

def test_spacing_punctuation():
    assert preprocess_address("Ул .Курильская 9") == "Ул. Курильская 9"

def test_split_glued():
    r = preprocess_address("66квартал 12дом 69квартира")
    assert "66 квартал" in r
    assert "12 дом" in r

def test_house_literal_preserved():
    assert "12а" in preprocess_address("ул. Ленина 12а кв 5")

def test_fractional_house():
    r = preprocess_address("Туран 55/6")
    assert "55/6" in r or "55 / 6" in r

def test_typos():
    assert "подъезд" in preprocess_address("4 подьезд")

def test_latin():
    assert "кв" in preprocess_address("flat 191").lower()

def test_confidence_high():
    r = compute_confidence({"city": "Алматы", "street_name": "Курильская", "house": "12"})
    assert r["score"] >= 0.7

def test_confidence_garbage():
    r = compute_confidence({"city": "Алматы", "street_name": "магазин береке", "house": "55"})
    assert len(r["warnings"]) > 0
