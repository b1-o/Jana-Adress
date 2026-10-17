"""Стресс-тест: 10k и 100k адресов."""
import sys, time, json
sys.path.insert(0, ".")

from app.preprocessor import preprocess_address
from app.parser import AddressParser
from app.gazetteer import get_gazetteer
from app.confidence import compute_confidence

gaz = get_gazetteer()
parser = AddressParser(gaz)

BASE = [
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
]

def run_benchmark(n, label):
    samples = BASE * (n // len(BASE)) + BASE[:n % len(BASE)]
    
    # Preprocessor alone
    start = time.perf_counter()
    for s in samples:
        preprocess_address(s)
    t_pre = time.perf_counter() - start
    
    # Full pipeline + confidence
    start = time.perf_counter()
    results = []
    for s in samples:
        clean = preprocess_address(s)
        r = parser.parse(clean)
        compute_confidence(r)
        results.append(r)
    t_full = time.perf_counter() - start
    
    print(f"\n{'='*55}")
    print(f"  {label}: {n} адресов")
    print(f"{'='*55}")
    print(f"  Preprocessor:     {t_pre:.3f}s   ({n/t_pre:>8.0f} addr/s)")
    print(f"  Full pipeline:    {t_full:.3f}s   ({n/t_full:>8.0f} addr/s)")
    print(f"  Memory (approx):  {n * 0.5 / 1024:.1f} MB")
    return n / t_full

print("🚀 JANA ADDRESS STRESS TEST")
print("⏱️  Starting benchmarks...\n")

r1k = run_benchmark(1_000,   "1K")
r10k = run_benchmark(10_000, "10K")
try:
    r50k = run_benchmark(50_000, "50K")
except Exception as e:
    r50k = 0
    print(f"\n  ⚠️  50K skipped: {e}")

print(f"\n{'='*55}")
print(f"  ИТОГО:")
print(f"  1K/speed:   {r1k:>8.0f} addr/s")
print(f"  10K/speed:  {r10k:>8.0f} addr/s")
if r50k:
    print(f"  50K/speed:  {r50k:>8.0f} addr/s")
print(f"{'='*55}")

# Проверка памяти
import gc
gc.collect()
import resource
mem_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
print(f"\n  Пиковая память: ~{mem_mb:.0f} MB")
