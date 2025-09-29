# app/Dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    gdal-bin \
    libgdal-dev \
    libproj-dev \
    libgeos-dev \
    gcc \
    g++ \
    make \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Непривилегированный пользователь
# RUN useradd -m appuser && chown -R appuser:appuser /
# USER appuser
