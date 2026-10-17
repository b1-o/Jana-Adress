PY ?= python3
API ?= http://localhost:8000

.PHONY: help up down logs test eval selfcheck serve build-gazetteer build-all fetch-osm clean check

help:
	@echo "make up              — docker compose up --build (главная команда сдачи)"
	@echo "make down            — остановить контейнеры"
	@echo "make serve           — запустить локально без Docker (uvicorn на :8000)"
	@echo "make test            — тесты парсера"
	@echo "make eval            — метрика на data/sample_input.json"
	@echo "make selfcheck       — самопроверка: справочник + 14 контрольных адресов"
	@echo "make check           — selfcheck + тесты + метрика (прогон перед сдачей)"
	@echo "make build-all       — пересобрать справочник (КАТО 2026 + районы 2024 + OSM)"
	@echo "make fetch-osm       — докачать улицы/жилмассивы по городам (нужна сеть)"

up:
	docker compose up --build

down:
	docker compose down

serve:
	$(PY) -m uvicorn app.main:app --host 0.0.0.0 --port 8000

test:
	$(PY) -m pytest tests -q || $(PY) tests/test_parser.py

selfcheck:
	$(PY) scripts/selfcheck.py

check: selfcheck test eval        # полная проверка перед сдачей

eval:
	$(PY) scripts/eval.py --input data/sample_input.json --expected data/sample_output.json

build-gazetteer:
	$(PY) scripts/build_kato.py data/source/КАТО_18.09.2026.xlsx
	$(PY) scripts/build_city_districts.py data/source/КАТО_18.12.2024.xls
	$(PY) scripts/build_gazetteer.py

build-all: build-gazetteer

fetch-osm:
	$(PY) scripts/fetch_osm.py --out data/osm

clean:
	-docker compose down
	find . -name __pycache__ -type d -exec rm -rf {} +
