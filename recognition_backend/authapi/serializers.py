from django.contrib.auth.models import User
from rest_framework import serializers
from django.contrib.auth import authenticate

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'password']
        extra_kwargs = {
            'email': {'required': False, 'allow_blank': True}  # если оставляем поле, но не требуем
        }

    def create(self, validated_data):
        validated_data.pop('email', None)
        user = User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password'],
            email=""
        )
        return user

class UserLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(**data)
        if user and user.is_active:
            return user
        raise serializers.ValidationError("Неверные учетные данные")