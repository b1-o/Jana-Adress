"""Бенчмарк пропускной способности. Запускать ДО и ПОСЛЕ оптимизаций."""
import sys, time, json
sys.path.insert(0, ".")

from app.preprocessor import preprocess_address
from app.parser import AddressParser
from app.gazetteer import get_gazetteer

gaz = get_gazetteer()
parser = AddressParser(gaz)

SAMPLES = [
    "66квартал 12дом 69квартира",
    "Ул .Курильская 9 кв 1",
    "Туран 55/6 магазин береке 4подьезд 9этаж",
    "Назарбаева8 flat 191",
    "Нурсити 2 микрорайон 11дом 5 подьезд 239 кв",
    "город Актобе/Ақтөбе қаласы, Мкр Аксай 3а, 59, кв 70",
    "Алматы, ул. Розыбакиева 100, кв 3",
    "жуалы19 кв 5",
    "Кулинская 15 подъезд 2 этаж 44",
    "Турксибский район, Рыбинский переулок, дом 4",
] * 100  # 1000 адресов

print(f"Бенчмарк: {len(SAMPLES)} адресов")
print("-" * 50)

# Тест 1: только preprocessor
start = time.perf_counter()
for s in SAMPLES:
    preprocess_address(s)
t_pre = time.perf_counter() - start
print(f"Preprocessor:     {t_pre:.3f}s  ({len(SAMPLES)/t_pre:.0f} addr/s)")

# Тест 2: полный pipeline
start = time.perf_counter()
results = [parser.parse(preprocess_address(s)) for s in SAMPLES]
t_full = time.perf_counter() - start
print(f"Full pipeline:    {t_full:.3f}s  ({len(SAMPLES)/t_full:.0f} addr/s)")

# Тест 3: средний confidence
from app.confidence import compute_confidence
scores = [compute_confidence(r)["score"] for r in results]
print(f"Avg confidence:   {sum(scores)/len(scores):.2f}")
print(f"-" * 50)
print(f"✅ ГОТОВО: {len(SAMPLES)} за {t_full:.2f}с = {len(SAMPLES)/t_full:.0f} addr/s")
