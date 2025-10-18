from django.urls import path

from .callbacks import image_location_callback, image_trash_result_callback
from .views import UploadImageView, GetUserImageLocationsView, DeleteUserImageLocationView, UploadArchiveView, \
    GetUserDetectedLocation

urlpatterns = [
    path('upload-archive/', UploadArchiveView.as_view(), name='upload_archive'),
    path('upload-images/', UploadImageView.as_view(), name='upload_images'),
    path('user/image-locations/', GetUserImageLocationsView.as_view(), name='user-image-locations'),
    path('update-image-result/', image_location_callback, name='image-location-callback'),
    path('update-image-trash-result/', image_trash_result_callback, name='image-trash-location-callback'),
    path('map/trash-images-by-coordinates/', GetUserDetectedLocation.as_view(), name='user-trash-image-locations'),
    path("image-locations/<int:pk>/", DeleteUserImageLocationView.as_view(), name="delete-image-location"),
]

# POST /api/upload-image/