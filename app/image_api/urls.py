from django.urls import path
from .views import UploadImageView

urlpatterns = [
    path('upload-images/', UploadImageView.as_view(), name='upload_images'),
]

# POST /api/upload-image/