from django.urls import path

from . import views
from .views import UploadImageView

urlpatterns = [
    path('upload-images/', UploadImageView.as_view(), name='upload_images'),
    path('upload/', views.upload_image, name='upload_image'),
]

# POST /api/upload-image/