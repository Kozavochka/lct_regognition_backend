from django.contrib.auth.models import User
from django.db import models
from django.conf import settings
from django.utils import timezone

class UploadedImage(models.Model):
    # Ссылка на пользователя, который загрузил файл
    # user = models.ForeignKey(
    #     settings.AUTH_USER_MODEL,
    #     on_delete=models.CASCADE,
    #     related_name='uploaded_images',
    #     help_text="Пользователь, загрузивший изображение"
    # )
    #
    # filename = models.CharField(max_length=255, help_text="Уникальное имя файла")
    # original_filename = models.CharField(max_length=255, blank=True, null=True, help_text="Оригинальное имя файла")
    # file_path = models.CharField(max_length=500, help_text="Относительный путь к файлу на сервере")
    # file_url = models.URLField(max_length=500, help_text="URL для доступа к файлу")
    # uploaded_at = models.DateTimeField(auto_now_add=True)
    filename = models.CharField(max_length=255, help_text="Уникальное имя файла")
    original_filename = models.CharField(max_length=255, blank=True, null=True, help_text="Оригинальное имя файла")
    file_path = models.CharField(max_length=500, default='', help_text="Относительный путь к файлу на сервере")
    s3_url = models.URLField(max_length=500, default='', help_text="URL для доступа к файлу")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"{self.filename} (загружено {self.user.username})"