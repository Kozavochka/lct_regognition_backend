from django.urls import path

from . import views
from .views import UploadImageView, GetUserImageLocationsView

urlpatterns = [
    path('upload-images/', UploadImageView.as_view(), name='upload_images'),
    path('user/image-locations/', GetUserImageLocationsView.as_view(), name='user-image-locations'),
    # path('upload/', views.upload_image, name='upload_image'),
]

# POST /api/upload-image/