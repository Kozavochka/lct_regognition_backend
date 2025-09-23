from rest_framework import serializers
from .models import Image

class ImageUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Image
        fields = ['id', 'title', 'image', 'uploaded_at']