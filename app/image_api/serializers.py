from rest_framework import serializers
from .models import UploadedImage


class UploadedImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = UploadedImage
        fields = ['id', 'filename', 's3_url', 'created_at']
        read_only_fields = ['id', 'created_at']