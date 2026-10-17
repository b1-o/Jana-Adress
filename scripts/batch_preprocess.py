#!/usr/bin/env python3
"""
Пакетная предобработка адресов из файла.
  python scripts/batch_preprocess.py input.csv output.csv
  python scripts/batch_preprocess.py input.json output.json
"""

import sys, json, csv
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.preprocessor import preprocess_address


def process_csv(inp: str, out: str):
    with open(inp, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        addr_col = next((c for c in fields if c.lower() in
                         ('address', 'адрес', 'addr', 'raw_address')), fields[0] if fields else None)
        if not addr_col:
            print("❌ Не найдена колонка с адресом"); return

        with open(out, 'w', encoding='utf-8', newline='') as o:
            writer = csv.DictWriter(o, fieldnames=fields + ['cleaned_address'])
            writer.writeheader()
            for row in reader:
                row['cleaned_address'] = preprocess_address(row.get(addr_col, ''))
                writer.writerow(row)
    print(f"✅ {inp} → {out}")


def process_json(inp: str, out: str):
    with open(inp, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, list):
        for item in data:
            for k in ('address', 'адрес', 'addr', 'raw_address'):
                if k in item:
                    item['cleaned_address'] = preprocess_address(item[k])
                    break
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ {inp} → {out}")


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python batch_preprocess.py <input> <output>"); sys.exit(1)
    inp, out = sys.argv[1], sys.argv[2]
    (process_json if inp.endswith('.json') else process_csv)(inp, out)
