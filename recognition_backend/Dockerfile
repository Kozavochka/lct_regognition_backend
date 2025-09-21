# Используем официальный образ Python как базовый
FROM python:3.11-slim

# Устанавливаем системные зависимости (если нужны, например, для psycopg2 или Pillow)
RUN apt-get update && apt-get install -y \
    gcc \
    libc6-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем локаль (опционально, но полезно для корректной работы с текстом)
ENV LANG C.UTF-8

# Создаём рабочую директорию внутри контейнера
WORKDIR /app

# Копируем requirements.txt и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код приложения
COPY . .

# Собираем статику (если используется collectstatic)
# RUN python manage.py collectstatic --noinput

# Открываем порт (по умолчанию Django использует 8000)
EXPOSE 8000

# Запускаем сервер разработки (для продакшена используй gunicorn или uwsgi)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]