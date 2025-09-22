from django.urls import path
from .views import UploadImageView

urlpatterns = [
    path('upload-image/', UploadImageView.as_view(), name='upload_image'),
]

# POST /api/upload-image/