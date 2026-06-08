FROM python:3.11-slim

WORKDIR /app

# Системные библиотеки: libpq (postgres), gcc (сборка),
# libGL/libglib (нужны для opencv/easyocr), poppler (pdf2image)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc g++ \
    libgl1 libglib2.0-0 \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway передаёт порт через $PORT. Локально по умолчанию 8000.
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]