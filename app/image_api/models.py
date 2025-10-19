from django.contrib.auth.models import User
from django.conf import settings
from django.db import models
from .services.s3_service import S3Service
import logging
from django.db.models.signals import post_delete
from django.dispatch import receiver

class UploadedImage(models.Model):
    filename = models.CharField(max_length=255, help_text="Уникальное имя файла")
    original_filename = models.CharField(max_length=255, blank=True, null=True, help_text="Оригинальное имя файла")
    file_path = models.CharField(max_length=500, default='', help_text="Относительный путь к файлу на сервере")
    s3_url = models.URLField(max_length=500, default='', help_text="URL для доступа к файлу")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"{self.filename} (загружено {self.user.username})"

    @property
    def preview_url(self):
        """
        Возвращает presigned URL для предпросмотра файла из S3.
        """
        s3_service = S3Service()
        return s3_service.generate_presigned_url(self.filename)


@receiver(post_delete, sender=UploadedImage)
def delete_file_from_s3(sender, instance, **kwargs):
    if instance.filename:
        s3 = S3Service()
        try:
            s3.delete_file(instance.filename)
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Ошибка при удалении {instance.filename} из S3: {e}")
        
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

    @property
    def status_display_ru(self):
        mapping = {
            'processing': 'Ожидает',
            'done': 'Готово',
            'failed': 'Ошибка',
        }
        return mapping.get(self.status, self.status)
    
    def to_dict(self):
        if self.lat is not None and self.lon is not None:
            main_coordinates = {"lat": self.lat, "lon": self.lon}
        else:
            main_coordinates = None

        trash_images = []
        for det in self.detected_image_mappings.all():
            trash_images.append({
                "id": det.id,
                "image": {
                    "id": det.file.id,
                    "filename": det.file.filename,
                    "file_path": det.file.s3_url or det.file.file_path,
                    "preview_url": det.file.preview_url,
                    # "preview_url": self.preview_url,
                    # preview_url можно тоже добавить, если нужно
                },
                "lat": det.lat,
                "lon": det.lon,
            })

        return {
            "id": self.id,
            "status": self.status_display_ru,
            "created_at": self.created_at.isoformat(),
            "user": {
                "id": self.user.id,
                "username": self.user.username,
            },
            "main_address": self.address,
            "height": self.height,
            "angle": self.angle,
            "error_reason": self.error_reason,
            "main_coordinates": main_coordinates,
            "main_image": {
                "id": self.image.id,
                "filename": self.image.filename,
                "file_path": self.file_path,
                "preview_url": self.preview_url,
            },
            "trash_images": trash_images,
        }
    
class UploadedArchive(models.Model):
    filename = models.CharField(max_length=255)
    original_filename = models.CharField(max_length=255)
    s3_url = models.URLField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    metadata_filename = models.CharField(max_length=255, null=True, blank=True)
    metadata_s3_url = models.URLField(null=True, blank=True)

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
    address = models.CharField(max_length=500, null=True, blank=True)

    def to_dict(self):
        return {
            'id': self.id,
            'image': {
                'id': self.file.id,
                'filename': self.file.filename,
                'original_filename': self.file.original_filename,
                'file_path': self.file.file_path,
                's3_url': self.file.s3_url,
                'preview_url': self.file.preview_url,
                'uploaded_at': self.file.uploaded_at.isoformat(),
            },
            'image_location_id': self.image_location_id,
            'lat': self.lat,
            'lon': self.lon,
            'created_at': self.created_at.isoformat(),
            'address': self.address,
        }