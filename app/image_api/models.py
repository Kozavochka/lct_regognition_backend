from django.contrib.auth.models import User
from django.conf import settings
from django.db import models
from .services.s3_service import S3Service


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

    address = models.CharField(max_length=500, null=True, blank=True)
    height = models.FloatField(null=True, blank=True)
    angle = models.FloatField(null=True, blank=True)
    error_reason = models.TextField(null=True, blank=True)
    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)

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

    @property
    def preview_url(self):
        """
        Возвращает presigned URL для предпросмотра файла.
        """
        s3 = S3Service()
        return s3.generate_presigned_url(self.image.filename)


    def to_dict(self):
        """
        Возвращает словарь с нужными полями для JSON-сериализации.
        """
        return {
            "id": self.id,
            "status": self.status,
            "address": self.address,
            "height": self.height,
            "angle": self.angle,
            "error_reason": self.error_reason,
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
                "preview_url": self.preview_url
            },
        }
    
class UploadedArchive(models.Model):
    filename = models.CharField(max_length=255)
    original_filename = models.CharField(max_length=255)
    s3_url = models.URLField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)


class DetectedImageLocation(models.Model):
    file = models.ForeignKey(
        'UploadedImage',
        on_delete=models.CASCADE,
        related_name='detected_locations',
    )

    image_location = models.ForeignKey(
        'ImageLocation',
        on_delete=models.CASCADE,
        related_name='detected_image_mappings'
    )

    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
