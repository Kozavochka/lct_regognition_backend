from rest_framework import serializers
from .models import UploadedImage, ImageLocation


class UploadedImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = UploadedImage
        fields = ['id', 'filename', 's3_url', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at']

class ImageLocationSerializer(serializers.ModelSerializer):
    lat = serializers.SerializerMethodField()
    lon = serializers.SerializerMethodField()
    file_path = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = ImageLocation
        fields = [
            'id',
            'user',
            'image',
            'lat',
            'lon',
            'file_path',
            'status',
            'status_display',
            'created_at'
        ]
        read_only_fields = ['created_at']

    def get_lat(self, obj):
        return obj.lat

    def get_lon(self, obj):
        return obj.lon

    def get_file_path(self, obj):
        return obj.file_path  # используем свойство модели

    def get_status_display(self, obj):
        # Если у модели нет метода get_status_display, можно вернуть просто status
        return obj.get_status_display() if hasattr(obj, 'get_status_display') else obj.status