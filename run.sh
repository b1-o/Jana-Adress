#!/usr/bin/env bash
# Запуск Jana Address на Linux/macOS: создаёт venv, ставит зависимости, поднимает сервер.
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo "== создаю виртуальное окружение =="
    python -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "== ставлю зависимости =="
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo "== тесты =="
python -m pytest tests -q

echo "== сервер: http://127.0.0.1:8000 =="
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
