from django.urls import path

from . import views
from .callbacks import image_location_callback
from .views import UploadImageView, GetUserImageLocationsView, DeleteUserImageLocationView

urlpatterns = [
    path('upload-images/', UploadImageView.as_view(), name='upload_images'),
    path('user/image-locations/', GetUserImageLocationsView.as_view(), name='user-image-locations'),
    path('update-result/', image_location_callback, name='image-location-callback'),
    path("image-locations/<int:pk>/", DeleteUserImageLocationView.as_view(), name="delete-image-location"),
    # path('upload/', views.upload_image, name='upload_image'),
]

# POST /api/upload-image/