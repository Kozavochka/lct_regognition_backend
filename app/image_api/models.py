from django.contrib.auth.models import User
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db import models

class UploadedImage(models.Model):
    filename = models.CharField(max_length=255, help_text="Уникальное имя файла")
    original_filename = models.CharField(max_length=255, blank=True, null=True, help_text="Оригинальное имя файла")
    file_path = models.CharField(max_length=500, default='', help_text="Относительный путь к файлу на сервере")
    s3_url = models.URLField(max_length=500, default='', help_text="URL для доступа к файлу")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"{self.filename} (загружено {self.user.username})"

class ImageLocation(models.Model):
    # Ссылка на пользователя
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='image_locations'
    )

    # Ссылка на загруженное изображение
    image = models.ForeignKey(
        'UploadedImage',
        on_delete=models.CASCADE,
        related_name='locations'
    )

    # Статус
    status = models.CharField(
        max_length=20,
        choices=[
            ('processing', 'Processing'),
            ('done', 'Done'),
            ('failed', 'Failed'),
        ],
        default='processing'
    )

    # Координаты (lat/lon) — вместо PointField
    lat = models.FloatField(null=True, blank=True, help_text="Широта")
    lon = models.FloatField(null=True, blank=True, help_text="Долгота")

    # Время создания
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'image_locations'
        verbose_name = 'Image Location'
        verbose_name_plural = 'Image Locations'

    def __str__(self):
        return f"Location for {self.image.filename} - {self.status}"

    @property
    def file_path(self):
        return self.image.s3_url or self.image.file_path

    def to_dict(self):
        """
        Возвращает словарь с нужными полями для JSON-сериализации.
        """
        return {
            "id": self.id,
            "status": self.status,
            "lat": self.lat,
            "lon": self.lon,
            "created_at": self.created_at.isoformat(),
            "user": {
                "id": self.user.id,
                "username": self.user.username,
            },
            "image": {
                "id": self.image.id,
                "filename": self.image.filename,
                "file_path": self.file_path,
            },
        }


class ServerImage(models.Model):
    filename = models.CharField(max_length=255, help_text="Уникальное имя файла")
    original_filename = models.CharField(max_length=255, blank=True, null=True, help_text="Оригинальное имя файла")
    file_path = models.CharField(max_length=500, help_text="Относительный путь к файлу на сервере")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    def get_absolute_url(self):
        from django.conf import settings
        import os
        return os.path.join(settings.MEDIA_URL, self.file_path)

class ServerImageLocation(models.Model):
    # Ссылка на пользователя
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='server_image_locations'
    )

    # Ссылка на изображение (теперь ServerImage)
    image = models.ForeignKey(
        'ServerImage',  # ← Изменено на ServerImage
        on_delete=models.CASCADE,
        related_name='server_locations'
    )

    # Статус
    status = models.CharField(
        max_length=20,
        choices=[
            ('processing', 'Processing'),
            ('done', 'Done'),
            ('failed', 'Failed'),
        ],
        default='processing'
    )

    # Координаты (lat/lon) — вместо PointField
    lat = models.FloatField(null=True, blank=True, help_text="Широта")
    lon = models.FloatField(null=True, blank=True, help_text="Долгота")

    # Время создания
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'server_image_locations'
        verbose_name = 'Server Image Location'
        verbose_name_plural = 'Server Image Location'

    def __str__(self):
        return f"Location for {self.image.filename} - {self.status}"

    @property
    def file_path(self):
        return self.image.get_absolute_url()  # ← Используем метод из ServerImage

    def to_dict(self):
        """
        Возвращает словарь с нужными полями для JSON-сериализации.
        """
        return {
            "id": self.id,
            "status": self.status,
            "lat": self.lat,
            "lon": self.lon,
            "created_at": self.created_at.isoformat(),
            "user": {
                "id": self.user.id,
                "username": self.user.username,
            },
            "image": {
                "id": self.image.id,
                "filename": self.image.filename,
                "file_path": self.file_path,
            },
        }