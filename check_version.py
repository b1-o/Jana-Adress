"""Проверка: какая версия проекта лежит в папке и что реально отдаёт сервер.

Запуск из корня проекта:

    python check_version.py

Скрипт ничего не меняет — только читает файлы и, если сервер запущен,
отправляет ему один тестовый адрес.
"""

from __future__ import annotations

import glob
import json
import os
import sys
import urllib.error
import urllib.request

OK = "OK  "
BAD = "!!  "

#: что должно быть в новых файлах
MARKERS = {
    "app/parser.py": ("_resolve_details", "фикс: квартира/подъезд/этаж не путаются"),
    "app/preprocessor.py": ("домм", "фикс: опечатки «домм», «етаж»"),
}

#: контрольный адрес: сервер должен вернуть подъезд=None, этаж=6, дом=117
TRICKY = "кожамкулова 117 кв 5 домм 100 этаж 6"
EXPECTED = {"house": "117", "apartment": "5", "entrance": None, "floor": "6"}


def check_files() -> list[str]:
    problems: list[str] = []
    print("== Файлы в папке " + os.getcwd() + " ==")

    for path, (marker, title) in MARKERS.items():
        if not os.path.exists(path):
            print(BAD + f"{path} — файла нет")
            problems.append(path)
            continue
        text = open(path, encoding="utf-8", errors="ignore").read()
        if marker in text:
            print(OK + f"{path} — {title}")
        else:
            print(BAD + f"{path} — СТАРЫЙ (нет «{marker}»)")
            problems.append(path)

    # requirements: pandas нужен только для пересборки справочника
    if os.path.exists("requirements.txt"):
        req = open("requirements.txt", encoding="utf-8", errors="ignore").read()
        if "pandas" in req:
            print(BAD + "requirements.txt — СТАРЫЙ (pandas внутри, pip упадёт на Python 3.13+)")
            problems.append("requirements.txt")
        else:
            print(OK + "requirements.txt — новый (pandas вынесен в requirements-data.txt)")
    else:
        print(BAD + "requirements.txt — файла нет")
        problems.append("requirements.txt")

    # интерфейс
    if os.path.exists("app/static/index.html"):
        size = os.path.getsize("app/static/index.html")
        kind = "прежний дизайн" if size > 40000 else "новый (короткий) дизайн"
        print(OK + f"app/static/index.html — {size} байт ({kind})")
    else:
        print(BAD + "app/static/index.html — файла нет")
        problems.append("app/static/index.html")

    # тесты
    tests = sorted(glob.glob("tests/test_*.py"))
    print(f"     тестовых файлов: {len(tests)}")
    if "tests/test_details_order.py" in tests:
        print(OK + "tests/test_details_order.py — есть (защита от перестановки)")
    else:
        print(BAD + "tests/test_details_order.py — НЕТ")
        problems.append("tests/test_details_order.py")

    return problems


def check_server(port: int = 8000) -> None:
    base = f"http://127.0.0.1:{port}"
    print(f"\n== Сервер на {base} ==")

    try:
        with urllib.request.urlopen(base + "/api/health", timeout=5) as resp:
            health = json.load(resp)
    except (urllib.error.URLError, OSError):
        print("     сервер не запущен — проверка «вживую» пропущена")
        print("     запусти в отдельном окне:  python -m uvicorn app.main:app --port 8000")
        return

    stats = health.get("gazetteer", {}).get("stats", {})
    print(OK + f"сервер отвечает: улиц {stats.get('streets')}, городов {stats.get('cities')}")

    body = json.dumps({"raw_address": TRICKY}).encode()
    req = urllib.request.Request(
        base + "/api/parse", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.load(resp)

    print(f"     проверочный адрес: {TRICKY}")
    bad = False
    for field, want in EXPECTED.items():
        got = result.get(field)
        mark = OK if got == want else BAD
        bad = bad or got != want
        print(f"     {mark}{field} = {got!r} (ждём {want!r})")

    if bad:
        print("\n     ВЫВОД: сервер работает на СТАРОМ коде.")
        print("     Файлы заменены, но процесс не перезапущен:")
        print("     Ctrl+C в окне uvicorn — и заново  python -m uvicorn app.main:app --port 8000")
    else:
        print("\n     ВЫВОД: сервер отдаёт правильный результат.")


def main() -> int:
    port = 8000
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])

    problems = check_files()
    check_server(port)

    print("\n" + "=" * 62)
    if problems:
        print("ИТОГ: в папке есть старые файлы — замени их и перезапусти сервер.")
        for p in problems:
            print("   • " + p)
        return 1
    print("ИТОГ: файлы в папке — актуальные.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
