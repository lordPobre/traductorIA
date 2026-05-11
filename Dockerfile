# 1. Usar una versión de Python oficial y ligera
FROM python:3.12-slim

# 2. Instalar el motor Tesseract OCR y Poppler (necesario para leer PDFs)
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-spa \
    tesseract-ocr-eng \
    poppler-utils \
    gcc \
    python3-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 3. Establecer la carpeta de trabajo
WORKDIR /app

# 4. Copiar e instalar tus librerías de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copiar todo tu código al servidor
COPY . .

# 6. El súper-comando para ejecutar Celery y Gunicorn juntos
CMD celery -A core worker -l info -c 1 & gunicorn core.wsgi --workers 1 --bind 0.0.0.0:$PORT