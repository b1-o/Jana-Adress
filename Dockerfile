# Jana Address — разбор адресных строк (кейс 1, Jana Post × Terricon Valley)
# Образ собирается один раз и работает автономно: справочник лежит внутри,
# интернет на этапе разбора не нужен.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GAZETTEER_PATH=data/gazetteer.sqlite

WORKDIR /app

# 1) зависимости (отдельным слоем — кешируется при правках кода)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) код и данные (справочник gazetteer.sqlite попадает в образ)
COPY app ./app
COPY scripts ./scripts
COPY tests ./tests
COPY data ./data

# 3) self-check при сборке: справочник на месте и парсер отвечает
RUN python -c "from app.parser import AddressParser as P; r = P().parse('город Алматы/Алматы қаласы, Мкр Аксай 3а, 59, кв 70'); assert r['city'] == 'Алматы' and r['street_name'] == 'Аксай 3а', r; print('self-check OK:', r['province'], r['city'], r['street_type'], r['street_name'], r['house'])"

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
