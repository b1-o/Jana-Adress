#!/usr/bin/env python3
"""
Генератор Jana Address Database.
Источники: КАТО (классификатор), OpenStreetMap (KZ), ручные данные.
Запуск: python scripts/build_db.py [--full]
"""

import sys
import json
import csv
import io
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import get_connection, init_db, db_stats, SCHEMA, DB_PATH
from app.database import AddressRepository, get_repo, norm_key


# =============================================================================
# Данные: области Казахстана (КАТО)
# =============================================================================
PROVINCES_KZ = [
    {"name_ru": "Актюбинская область", "name_kz": "Ақтөбе облысы", "code_kato": "15"},
    {"name_ru": "Алматинская область", "name_kz": "Алматы облысы", "code_kato": "19"},
    {"name_ru": "Атырауская область", "name_kz": "Атырау облысы", "code_kato": "23"},
    {"name_ru": "Восточно-Казахстанская область", "name_kz": "Шығыс Қазақстан облысы", "code_kato": "31"},
    {"name_ru": "Жамбылская область", "name_kz": "Жамбыл облысы", "code_kato": "27"},
    {"name_ru": "Карагандинская область", "name_kz": "Қарағанды облысы", "code_kato": "29"},
    {"name_ru": "Костанайская область", "name_kz": "Қостанай облысы", "code_kato": "39"},
    {"name_ru": "Кызылординская область", "name_kz": "Қызылорда облысы", "code_kato": "43"},
    {"name_ru": "Мангистауская область", "name_kz": "Маңғыстау облысы", "code_kato": "47"},
    {"name_ru": "Павлодарская область", "name_kz": "Павлодар облысы", "code_kato": "55"},
    {"name_ru": "Северо-Казахстанская область", "name_kz": "Солтүстік Қазақстан облысы", "code_kato": "59"},
    {"name_ru": "Южно-Казахстанская область", "name_kz": "Оңтүстік Қазақстан облысы", "code_kato": "63"},
    {"name_ru": "Астана", "name_kz": "Астана", "code_kato": "71", "type": "city"},
    {"name_ru": "Алматы", "name_kz": "Алматы", "code_kato": "75", "type": "city"},
    {"name_ru": "Шымкент", "name_kz": "Шымкент", "code_kato": "79", "type": "city"},
]

# Код КАТО области -> ID (заполняется после insert)
PROVINCE_MAP: dict[str, int] = {}


# =============================================================================
# Городов - ключевые для Jana Post
# =============================================================================
CITIES_KZ = [
    # Астана
    {"name": "Астана", "kato": "71", "province_kato": "71", "lat": 51.1694, "lon": 71.4492},
    # Алматы
    {"name": "Алматы", "kato": "75", "province_kato": "75", "lat": 43.2220, "lon": 76.8512},
    # Шымкент
    {"name": "Шымкент", "kato": "79", "province_kato": "79", "lat": 42.3150, "lon": 69.5860},
    # Актобе
    {"name": "Актобе", "kato": "1500000", "province_kato": "15", "lat": 50.2797, "lon": 57.2075},
    # Караганда
    {"name": "Караганда", "kato": "2900000", "province_kato": "29", "lat": 49.8156, "lon": 73.0995},
    # Костанай
    {"name": "Костанай", "kato": "3900000", "province_kato": "39", "lat": 53.2205, "lon": 63.6454},
    # Кызылорда
    {"name": "Кызылорда", "kato": "4300000", "province_kato": "43", "lat": 44.8505, "lon": 65.5027},
    # Павлодар
    {"name": "Павлодар", "kato": "5500000", "province_kato": "55", "lat": 52.3244, "lon": 
