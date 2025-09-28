import os
import uuid
import boto3
import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.files.base import ContentFile

from .models import UploadedImage
from .serializers import UploadedImageSerializer
from .services.s3_service import S3Service

logger = logging.getLogger(__name__)


class UploadImageView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        files = request.FILES.getlist("image")

        if not files:
            return Response({"error": "No files uploaded"}, status=status.HTTP_400_BAD_REQUEST)

        s3_service = S3Service()

        # Сначала валидируем все файлы
        validated_files = []
        validation_errors = []

        for i, file_obj in enumerate(files):
            try:
                if not file_obj:
                    validation_errors.append({
                        "file_index": i,
                        "filename": f"file_{i}",
                        "error": "Empty or missing file"
                    })
                    continue

                filename = f"{uuid.uuid4()}_{file_obj.name}"
                file_content = file_obj.read()

                validated_files.append({
                    'filename': filename,
                    'content': file_content,
                    'original_filename': file_obj.name,
                    'index': i,
                    'content_type': getattr(file_obj, 'content_type', 'application/octet-stream')
                })

            except Exception as e:
                validation_errors.append({
                    "file_index": i,
                    "filename": file_obj.name if file_obj else f"file_{i}",
                    "error": str(e)
                })

        if validation_errors:
            return Response({
                "validation_errors": validation_errors
            }, status=status.HTTP_400_BAD_REQUEST)

        uploaded_images = []
        upload_errors = []

        try:
            # Загружаем файлы в S3
            upload_results = s3_service.batch_upload(validated_files)

            # Обрабатываем успешные загрузки
            for success_file in upload_results['successful']:
                try:
                    # Сохраняем в БД
                    uploaded = UploadedImage.objects.create(
                        filename=success_file['filename'],
                        original_filename=success_file['original_filename'],
                        file_path=f"uploads/{success_file['filename']}",  # можно настроить как нужно
                        s3_url=success_file['url'],
                        user_id=request.user.id  # или request.user если используется foreign key
                    )
                    uploaded_images.append(uploaded)
                    logger.info(f"Database record created: {success_file['filename']}")
                except Exception as db_error:
                    logger.error(f"Database error for {success_file['filename']}: {str(db_error)}")
                    # Если не удалось сохранить в БД, удаляем файл из S3
                    s3_service.delete_file(success_file['filename'])
                    upload_errors.append({
                        "file_index": success_file['index'],
                        "filename": success_file['original_filename'],
                        "error": f"Database error: {str(db_error)}"
                    })

            # Обрабатываем ошибки загрузки
            upload_errors.extend(upload_results['failed'])

            if upload_errors:
                # Откатываем уже загруженные файлы
                self._rollback_uploaded_files(uploaded_images, s3_service)

                return Response({
                    "error": "Upload failed",
                    "details": "Server error occurred during file upload"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            serializer = UploadedImageSerializer(uploaded_images, many=True)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Critical error: {str(e)}")
            self._rollback_uploaded_files(uploaded_images, s3_service)

            return Response({
                "error": "Upload failed",
                "details": "Server error occurred during file upload"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _rollback_uploaded_files(self, uploaded_images, s3_service):
        """
        Откатывает уже загруженные файлы при ошибке
        """
        for uploaded_image in uploaded_images:
            try:
                uploaded_image.delete()
                s3_service.delete_file(uploaded_image.filename)
            except Exception as delete_error:
                logger.error(f"Error deleting {uploaded_image.filename}: {str(delete_error)}")


from rest_framework.decorators import api_view
from rest_framework.response import Response

def mock_external_api(image):
    """
    Метод-заглушка, имитирующий ответ внешнего API.
    """
    # Здесь можно сымитировать обработку изображения
    # и вернуть нужные данные
    return {
        'id': 1,
        'file_id': 123,
        'status': 'success',
        'lat': '55.7558',
        'lon': '37.6173',
        'address': 'Москва, Красная площадь'
    }

@api_view(['POST'])
def upload_image(request):
    image = request.FILES.get('image')

    if not image:
        return Response({'error': 'No image provided'}, status=400)

    # Вызываем заглушку вместо внешнего API
    external_data = mock_external_api(image)

    # Формируем нужный JSON
    result = {
        'id': external_data.get('id'),
        'file_id': external_data.get('file_id'),
        'status': external_data.get('status'),
        'lat': external_data.get('lat'),
        'lon': external_data.get('lon'),
        'address': external_data.get('address'),
    }

    return Response(result, status=200)