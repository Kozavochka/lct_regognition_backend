# /app/scripts/process_csv.py
import os
import sys
import django
from django.conf import settings

# --- Настройка Django ---
DJANGO_SETTINGS_MODULE = 'recognition_backend.settings'

# Добавляем путь к папке, содержащей recognition_backend (в данном случае это /app/)
# Это позволяет Python найти модуль recognition_backend при импорте.
sys.path.append('/app')

# Устанавливаем переменную окружения для Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', DJANGO_SETTINGS_MODULE)

# Загружаем настройки Django
django.setup()

# --- Теперь можно импортировать модели Django ---
import io
import pandas as pd
import botocore
from django.contrib.auth import get_user_model
from image_api.models import UploadedImage, ImageLocation
from image_api.services.s3_service import S3Service

# --- параметры ---
CSV_FILENAME = "table.csv"           # имя CSV-файла в S3
HARDCODED_USER_ID = 1                 # id пользователя

# --- инициализация ---
User = get_user_model()
user = User.objects.get(id=HARDCODED_USER_ID)
s3 = S3Service()

# --- скачиваем CSV из S3 ---
obj = s3.s3_client.get_object(Bucket=s3.bucket_name, Key=CSV_FILENAME)
csv_bytes = obj["Body"].read()

# Декодируем и читаем CSV
csv_string = csv_bytes.decode('utf-8-sig')
df = pd.read_csv(io.StringIO(csv_string), sep=';')

# Ожидаем, что в CSV есть колонки: "image", "lat", "lon"
for idx, row in df.iterrows():
    image_key = row["image"]
    lat = row["lat"]
    lon = row["lon"]

    try:
        # --- пробуем скачать картинку из S3 ---
        img_obj = s3.s3_client.get_object(Bucket=s3.bucket_name, Key=image_key)
        img_bytes = img_obj["Body"].read()
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            print(f"⚠️  Строка {idx}: файл {image_key} не найден в S3, пропускаем")
            continue
        else:
            raise  # другие ошибки пусть падают

    # --- создаём UploadedImage ---
    uploaded = UploadedImage.objects.create(
        filename=image_key.split("/")[-1],
        original_filename=image_key,
        file_path=image_key,
        s3_url=s3.generate_file_url(image_key),
        user=user
    )

    # --- создаём ImageLocation ---
    ImageLocation.objects.create(
        user=user,
        image=uploaded,
        status="done",
        lat=lat,
        lon=lon
    )

    print(f"✅ Строка {idx}: создано UploadedImage + ImageLocation для {image_key}")
