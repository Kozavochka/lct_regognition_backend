from rest_framework import serializers
from .models import UploadedImage, ImageLocation, DetectedImageLocation


class UploadedImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = UploadedImage
        fields = ['id', 'filename', 's3_url', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at']

class ImageLocationSerializer(serializers.ModelSerializer):
    address = serializers.CharField(allow_null=True, required=False)
    height = serializers.FloatField(allow_null=True, required=False)
    angle = serializers.FloatField(allow_null=True, required=False)
    error_reason = serializers.CharField(allow_null=True,required=False)
    file_path = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = ImageLocation
        fields = [
            'id',
            'user',
            'image',
            'address',
            'height',
            'angle',
            'error_reason',
            'file_path',
            'status',
            'status_display',
            'created_at'
        ]
        read_only_fields = ['created_at']

    def get_file_path(self, obj):
        return obj.file_path  # используем свойство модели

    def get_status_display(self, obj):
        # Если у модели нет метода get_status_display, можно вернуть просто status
        return obj.get_status_display() if hasattr(obj, 'get_status_display') else obj.status

class DetectedImageLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetectedImageLocation
        fields = [
            'id',
            'file',
            'image_location',
            'lat',
            'lon',
            'created_at',
        ]
        read_only_fields = ['created_at']