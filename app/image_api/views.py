import json
import os
import uuid
import boto3
import logging

from django.conf import settings
from django.contrib.auth.models import User
import requests
from django.core.files.storage import default_storage
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.files.base import ContentFile

from .models import UploadedImage, ImageLocation, ServerImage, ServerImageLocation
from .pagination import CustomPagination
from .serializers import UploadedImageSerializer, ImageLocationSerializer
from .services.s3_service import S3Service
from .tasks import process_geo_tasks


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
                image_locations.append(location)

            # Подготавливаем массив данных для отправки в _send_geo_request
            images_data = []
            for uploaded_image in uploaded_images:
                images_data.append({
                    'image_id': uploaded_image.id,
                    # 'image_path': uploaded_image.s3_url,
                    'image_path': uploaded_image.filename
                })

            # Вызываем API один раз с массивом
            # geo_result = self._send_geo_request(images_data)
            process_geo_tasks.delay(images_data)

            # # Если нужно — обновить статусы ImageLocation на основе ошибок или успеха
            # # Например, пометить как 'failed' те, у которых есть ошибка
            # if geo_result:
            #     for error in geo_result['errors']:
            #         task_id = error['task_id']
            #         try:
            #             # Находим ImageLocation по task_id (который совпадает с image_id)
            #             location = ImageLocation.objects.get(image__id=int(task_id))
            #             location.status = 'failed'
            #             location.save()
            #         except ImageLocation.DoesNotExist:
            #             logger.warning(f"ImageLocation not found for task_id={task_id}")

            # Возвращаем пустое тело с 200 OK
            return Response({}, status=status.HTTP_200_OK)

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


    # def _send_geo_request(self, images):
    #     """
    #     Отправляет POST-запрос на внешний сервис для обработки списка изображений.
    #
    #     Args:
    #         images (list): Список словарей с ключами 'image_id' и 'image_path'.
    #
    #     Returns:
    #         dict: {
    #             'success': list of task_ids successfully queued,
    #             'errors': list of dicts with {'task_id', 'error'},
    #             'raw_response': original response dict (optional)
    #         }
    #     """
    #     callback_url = f"{settings.API_BASE_URL}:80/api/update-image-result/"
    #     url = f"{settings.EXTERNAL_SERVICE_URL}:5000/api/Prediction"
    #
    #     tasks = []
    #     for img in images:
    #         image_id = img['image_id']
    #         image_path = img['image_path']
    #         tasks.append({
    #             "fileName": image_path,
    #             "taskId": str(image_id)
    #         })
    #
    #     payload = {
    #         "callbackUrl": callback_url,
    #         "tasks": tasks
    #     }
    #
    #     headers = {
    #         "Content-Type": "application/json",
    #         "Accept": "*/*"
    #     }
    #
    #     try:
    #         logger.info(f"Sending geo request for {len(tasks)} images")
    #         logger.debug(f"Payload: {json.dumps(payload, indent=2)}")
    #
    #         response = requests.post(url, data=json.dumps(payload), headers=headers, timeout=30)
    #
    #         logger.info(f"Geo service response status: {response.status_code}")
    #
    #         if response.status_code == 202:
    #             try:
    #                 result = response.json()
    #                 logger.info(f"Geo service returned: {result}")
    #
    #                 # Извлекаем успешные job и ошибки
    #                 jobs = result.get("jobs", [])
    #                 validation_errors = result.get("validationErrors", [])
    #
    #                 # Формируем структурированный ответ
    #                 structured_result = {
    #                     'success': [job for job in jobs],  # можно преобразовать в int, если нужно
    #                     'errors': [
    #                         {
    #                             'task_id': error.get('taskId'),
    #                             'error': error.get('error')
    #                         }
    #                         for error in validation_errors
    #                     ],
    #                     'raw_response': result  # опционально, для отладки
    #                 }
    #
    #                 return structured_result
    #
    #             except ValueError:
    #                 logger.error("Geo service returned invalid JSON")
    #                 return {
    #                     'success': [],
    #                     'errors': [],
    #                     'raw_response': None
    #                 }
    #         else:
    #             logger.error(f"Geo service returned non-202 status: {response.status_code}, body: {response.text}")
    #             return {
    #                 'success': [],
    #                 'errors': [],
    #                 'raw_response': None
    #             }
    #
    #     except Exception as e:
    #         logger.error(f"Exception while calling geo service: {e}", exc_info=True)
    #         return {
    #             'success': [],
    #             'errors': [],
    #             'raw_response': None
    #         }

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
        image_locations = ImageLocation.objects.filter(user=user).select_related('image', 'user')

        # Пагинация
        paginator = CustomPagination()
        paginated_locations = paginator.paginate_queryset(image_locations, request)

        # Формируем список словарей через to_dict()
        response_data = [loc.to_dict() for loc in paginated_locations]

        # Возвращаем ответ с пагинацией
        return paginator.get_paginated_response(response_data)


class ImageUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        print("FILES:", request.FILES)  # 👈 добавьте эту строку
        print("FILES keys:", list(request.FILES.keys()))  # 👈 и эту

        files = request.FILES.getlist("image")

        if not files:
            return Response({"error": "No files uploaded"}, status=status.HTTP_400_BAD_REQUEST)

        # Валидация файлов
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

                # filename = f"{uuid.uuid4()}_{file_obj.name}"
                filename = file_obj.name
                validated_files.append({
                    'filename': filename,
                    'file_obj': file_obj,
                    'original_filename': file_obj.name,
                    'index': i,
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

        saved_images = []
        save_errors = []

        try:
            # Сохраняем файлы на сервер
            for validated_file in validated_files:
                try:
                    file_path = os.path.join('uploads', validated_file['filename'])
                    file_path_on_disk = default_storage.save(file_path, ContentFile(validated_file['file_obj'].read()))

                    # fake_path = os.path.join(r"C:\Downloads\lct", validated_file['filename'])
                    filename = validated_file['filename'].replace('/', os.sep)
                    fake_path = os.path.join(r"C:\Downloads\lct", filename)

                    server_image = ServerImage.objects.create(
                        filename=validated_file['filename'],
                        original_filename=validated_file['original_filename'],
                        # file_path=file_path_on_disk,
                        file_path=fake_path,
                        user=request.user
                    )
                    saved_images.append(server_image)

                    # Создаём ImageLocation со статусом 'processing'
                    location = ServerImageLocation.objects.create(
                        user=request.user,
                        image=server_image,
                        status='processing',
                        lat=None,
                        lon=None
                    )

                    # Отправляем запрос в geo-сервис и получаем jobId
                    result = self._send_geo_request(server_image.id, server_image.file_path)

                    if result and 'jobId' in result:
                        # Можно сохранить jobId, если нужно, в будущем
                        pass
                    else:
                        # Ошибка при вызове geo-сервиса
                        location.status = 'failed'  # или оставить 'processing'
                        location.save()

                except Exception as e:
                    logger.error(f"Error saving file {validated_file['filename']}: {str(e)}")
                    save_errors.append({
                        "file_index": validated_file['index'],
                        "filename": validated_file['original_filename'],
                        "error": str(e)
                    })

            if save_errors:
                # Откат при ошибках
                for img in saved_images:
                    try:
                        if default_storage.exists(img.file_path):
                            default_storage.delete(img.file_path)
                        img.delete()
                    except Exception as e:
                        logger.error(f"Rollback error for {img.filename}: {e}")

                return Response({
                    "error": "Upload failed",
                    "details": "Server error occurred during file upload"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Возвращаем результаты
            image_locations = [loc for loc in ServerImageLocation.objects.filter(image__in=saved_images)]
            response_data = [loc.to_dict() for loc in image_locations]

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Critical error: {str(e)}")
            for img in saved_images:
                try:
                    if default_storage.exists(img.file_path):
                        default_storage.delete(img.file_path)
                    img.delete()
                except Exception as e2:
                    logger.error(f"Rollback error for {img.filename}: {e2}")

            return Response({
                "error": "Upload failed",
                "details": "Server error occurred during file upload"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _send_geo_request(self, image_id, image_path):
        """
        Отправляет POST-запрос на внешний сервис для обработки изображения.
        """
        callback_url = "http://127.0.0.1:80/api/update-image-result/"
        # url = "http://51.250.115.228:8080/api/Prediction"
        url = "http://host.docker.internal:5000/api/Prediction"

        # Путь к файлу на диске (абсолютный)
        full_file_path = image_path

        payload = {
            "callbackUrl": callback_url,
            "tasks": [
                {
                    "filePath": full_file_path,
                    "taskId": str(image_id)
                }
            ]
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "*/*"
        }

        try:
            logger.info(f"Sending geo request for image {image_id} with path: {full_file_path}")
            logger.debug(f"Payload: {json.dumps(payload, indent=2)}")

            response = requests.post(url, data=json.dumps(payload), headers=headers, timeout=30)

            logger.info(f"Geo service response status: {response.status_code}")

            if response.status_code == 202:
                try:
                    result = response.json()
                    logger.info(f"Geo service returned: {result}")
                    return result  # вернём весь ответ, чтобы можно было достать jobId
                except ValueError:
                    logger.error("Geo service returned invalid JSON")
                    return None
            else:
                logger.error(f"Geo service returned non-202 status: {response.status_code}, body: {response.text}")
                return None

        except Exception as e:
            logger.error(f"Exception while calling geo service: {e}", exc_info=True)
            return None
        #     response = requests.post(
        #         "http://host.docker.internal:5000/api/Prediction",  # URL внешнего сервиса
        #         json=payload,
        #         headers=headers
        #     )
        #     if response.status_code == 202:
        #         # Здесь можно вернуть ответ, если нужно обработать сразу
        #         return True
        #     else:
        #         print(f"Geo service returned status {response.status_code}")
        #         return None
        # except Exception as e:
        #     print(f"Failed to call geo service: {e}")
        #     return None