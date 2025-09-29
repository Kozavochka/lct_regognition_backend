import os
import uuid
import boto3
import logging

from django.contrib.auth.models import User
import requests
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.files.base import ContentFile

from .models import UploadedImage, ImageLocation
from .pagination import CustomPagination
from .serializers import UploadedImageSerializer, ImageLocationSerializer
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
                    # Сохраняем в БД как UploadedImage
                    uploaded = UploadedImage.objects.create(
                        filename=success_file['filename'],
                        original_filename=success_file['original_filename'],
                        file_path=f"uploads/{success_file['filename']}",
                        s3_url=success_file['url'],
                        user=request.user
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

            # Создаём ImageLocation записи с status='processing', затем обновляем
            image_locations = []
            for uploaded_image in uploaded_images:
                location = ImageLocation.objects.create(
                    user=request.user,
                    image=uploaded_image,
                    status='processing',
                    lat=None,
                    lon=None
                )

                # Вызываем API синхронно
                geo_data = self._mock_external_api_call(uploaded_image.id, uploaded_image.s3_url)

                if geo_data:
                    location.lat = float(geo_data['lat'])
                    location.lon = float(geo_data['lot'])
                    location.status = 'done'
                else:
                    location.status = 'done'  # или 'failed', если хотите отдельный статус

                location.save()
                image_locations.append(location)

            # Сериализуем ImageLocation
            # serializer = ImageLocationSerializer(image_locations, many=True)
            # return Response(serializer.data, status=status.HTTP_200_OK)
            response_data = [loc.to_dict() for loc in image_locations]
            return Response(response_data, status=status.HTTP_200_OK)

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

    def _process_images_with_external_api(self, uploaded_images, user_id):
        """
        Отправляет ID изображений на внешнее API и сохраняет результаты
        """
        user = User.objects.get(id=user_id)

        results = []  # Список результатов для возврата

        for uploaded_image in uploaded_images:
            try:
                # Заменяем запрос на внешнее API на заглушку
                response_data = self._mock_external_api_call(uploaded_image.id, uploaded_image.s3_url)

                # Имитируем статус ответа (предполагаем, что заглушка возвращает данные)
                if response_data:  # Считаем, что если данные есть, то это "успешный" ответ
                    result_data = response_data

                    # Получаем lat и lon из ответа
                    lat = result_data.get('lat')
                    lon = result_data.get('lot')  # или 'lon' если API возвращает longitude так

                    # Проверяем и конвертируем координаты
                    lat_f = None
                    lon_f = None
                    try:
                        if lat is not None and lon is not None:
                            lat_f = float(lat)
                            lon_f = float(lon)
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid coordinates for image {uploaded_image.id}: lat={lat}, lon={lon}")

                    # Создаем запись с результатами
                    # Предполагается, что ImageLocation теперь имеет поля lat и lon вместо location (PointField)
                    image_location = ImageLocation.objects.create(
                        user=user,  # ForeignKey на User
                        image=uploaded_image,  # ForeignKey на UploadedImage
                        lat=lat_f,  # Новое поле для широты
                        lon=lon_f,  # Новое поле для долготы
                        address=result_data.get('address')
                    )

                    # Возвращаем информацию
                    result = {
                        'image_location_id': image_location.id,
                        'image_id': uploaded_image.id,
                        'user': {
                            'user_id': image_location.user.id,
                            'username': image_location.user.username
                        },
                        'lat': lat_f,
                        'lon': lon_f,  # используем 'lon' вместо 'lot'
                        'address': result_data.get('address'),
                        'status': 'success'
                    }

                else:
                    logger.error(f"Mock API returned no data for image {uploaded_image.id}")
                    # Создаем запись без координат
                    image_location = ImageLocation.objects.create(
                        user=user,
                        image=uploaded_image,
                        lat=None,  # Устанавливаем как None
                        lon=None,  # Устанавливаем как None
                        address=None
                    )

                    result = {
                        'image_location_id': image_location.id,
                        'image_id': uploaded_image.id,
                        'user': {
                            'user_id': image_location.user.id,
                            'username': image_location.user.username
                        },
                        'lat': None,
                        'lon': None,
                        'address': None,
                        'status': 'api_error'
                    }

            except Exception as e:
                logger.error(f"Error processing image {uploaded_image.id}: {str(e)}")
                # В случае ошибки также создаем запись, но без данных
                image_location = ImageLocation.objects.create(
                    user=user,
                    image=uploaded_image,
                    lat=None,
                    lon=None,
                    address=None
                )

                result = {
                    'image_location_id': image_location.id,
                    'image_id': uploaded_image.id,
                    'user': {
                        'user_id': image_location.user.id,
                        'username': image_location.user.username
                    },
                    'lat': None,
                    'lon': None,
                    'address': None,
                    'status': 'processing_error',
                    'error': str(e)
                }

            results.append(result)

        return results

    def _mock_external_api_call(self, image_id, image_url):
        """
        Функция-заглушка для имитации внешнего API
        Возвращает примерный ответ, который мог бы вернуть внешний API
        """
        import random

        # Симулируем случайный результат
        # В реальности вы можете вернуть фиксированные данные или случайные
        mock_responses = [
            {
                "lat": "55.7558",
                "lot": "37.6173",  # или "lon"
                "address": "Москва, Красная площадь, 1"
            },
            {
                "lat": "48.8566",
                "lot": "2.3522",
                "address": "Париж, Франция"
            },
            {
                "lat": "40.7128",
                "lot": "-74.0060",
                "address": "Нью-Йорк, США"
            },
            {
                "lat": "51.5074",
                "lot": "-0.1278",
                "address": "Лондон, Великобритания"
            },
            # Возвращаем None для симуляции ошибки
            None
        ]

        # С вероятностью 1 из 5 возвращаем None (ошибка)
        if random.randint(1, 5) == 1:
            return None

        # Выбираем случайный успешный ответ
        return random.choice(mock_responses[:-1])  # исключаем None из выбора

class GetUserImageLocationsView(APIView):
    def get(self, request, *args, **kwargs):
        # Получаем текущего пользователя
        user = request.user

        if not user.is_authenticated:
            return Response(
                {"error": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Фильтруем ImageLocation по пользователю
        image_locations = ImageLocation.objects.order_by('-id').filter(user=user).select_related('image', 'user')

        # Пагинация
        paginator = CustomPagination()
        paginated_locations = paginator.paginate_queryset(image_locations, request)

        # Формируем список словарей через to_dict()
        response_data = [loc.to_dict() for loc in paginated_locations]

        # Возвращаем ответ с пагинацией
        return paginator.get_paginated_response(response_data)
    
class DeleteUserImageLocationView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk, *args, **kwargs):
        user = request.user

        try:
            # Ищем объект только у текущего пользователя
            image_location = ImageLocation.objects.get(id=pk, user=user)
        except ImageLocation.DoesNotExist:
            return Response(
                {"error": "ImageLocation not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Удаляем объект
        image_location.delete()
        return Response({"message": f"ImageLocation {pk} deleted"}, status=status.HTTP_200_OK)    