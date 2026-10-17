import sys, csv, json
sys.path.insert(0, ".")
from app.gazetteer import get_gazetteer
from app.preprocessor import preprocess_address
from app.textnorm import norm_key

def check_file(filepath):
    gaz = get_gazetteer()
    
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        text = f.read(1024)
        f.seek(0)
        if text.strip().startswith(('[', '{')):
            data = json.load(f)
            rows = [item.get("raw_address") or item.get("address") or "" 
                    for item in (data if isinstance(data, list) else [data])]
        else:
            reader = csv.DictReader(f)
            col = next((c for c in (reader.fieldnames or []) if any(x in c.lower() for x in ('адрес', 'address'))), reader.fieldnames[0])
            rows = [r[col] for r in reader]

    total = len(rows)
    found_city, found_street, found_living = 0, 0, 0
    missed = []

    print(f"\n📊 Проверяем {total} адресов против справочника (+ aliases)...\n")
    for addr in rows:
        clean = preprocess_address(addr)
        words = norm_key(clean).split()
        
        c_ok = any(gaz.find_city(w) for w in words if len(w) > 2)
        s_ok = any(gaz.find_street(w) for w in words if len(w) > 2)
        # проверка по отдельным словам и биграммам ("нурсити 2")
        l_ok = any(gaz.find_living_area(w) for w in words if len(w) > 2)
        if not l_ok and len(words) >= 2:
            for j in range(len(words) - 1):
                pair = f"{words[j]} {words[j+1]}"
                if gaz.find_living_area(pair):
                    l_ok = True
                    break

        if c_ok: found_city += 1
        if s_ok: found_street += 1
        if l_ok: found_living += 1
        if not (c_ok or s_ok or l_ok):
            missed.append(addr)

    print(f"Город найден:         {found_city}/{total} ({found_city/total*100:.0f}%)")
    print(f"Улица найдена:        {found_street}/{total} ({found_street/total*100:.0f}%)")
    print(f"Жилой массив / ЖК:    {found_living}/{total} ({found_living/total*100:.0f}%)")
    
    recognized = total - len(missed)
    print(f"\n🎯 Итого распознано объектов: {recognized}/{total} ({recognized/total*100:.0f}%)")
    if missed:
        print("\nНе найдено:")
        for m in missed:
            print(f"  - {m}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_coverage.py <file.csv/json>")
        sys.exit(1)
    check_file(sys.argv[1])
