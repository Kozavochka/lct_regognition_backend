import uuid
import logging

from django.utils.dateparse import parse_date
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema, OpenApiParameter
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from geopy.geocoders import Nominatim

from .filters import ImageLocationDateFilter, RadiusFilter
from .models import ImageLocation, DetectedImageLocation
from .pagination import CustomPagination
from image_api.services.image_upload_service import ImageUploadService
from image_api.services.archive_upload_service import ArchiveUploadService
from .serializers import UploadImagesRequestSerializer, ImageDataSerializer

logger = logging.getLogger(__name__)

DEFAULT_ANGLE=0
DEFAULT_HEIGHT=1.5

# --- UploadImageView ---
# Схема успешного ответа
upload_success_response_schema = {
    "type": "object",
    "properties": {},
    "additionalProperties": False
}

# Схема ошибки валидации
upload_validation_error_schema = {
    "type": "object",
    "properties": {
        "validation_errors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file_index": {"type": "integer"},
                    "filename": {"type": "string"},
                    "error": {"type": "string"}
                },
                "required": ["file_index", "filename", "error"]
            }
        }
    },
    "required": ["validation_errors"]
}

# Схема серверной ошибки
upload_server_error_schema = {
    "type": "object",
    "properties": {
        "error": {"type": "string"},
        "details": {"type": "string"}
    },
    "required": ["error", "details"]
}

@extend_schema(
    request={
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'images_data[][image]': {
                    'type': 'array',
                    'items': {
                        'type': 'string',
                        'format': 'binary'
                    },
                    'description': 'Файл изображения (множественные параметры)',
                },
                'images_data[][address]': {
                    'type': 'string',
                    'description': 'Адрес местоположения изображения (необязательно, если есть lat/lon)',
                },
                'images_data[][lat]': {
                    'type': 'number',
                    'format': 'float',
                    'description': 'Широта (необязательно, если есть address)',
                },
                'images_data[][lon]': {
                    'type': 'number',
                    'format': 'float',
                    'description': 'Долгота (необязательно, если есть address)',
                },
                'images_data[][angle]': {
                    'type': 'number',
                    'format': 'float',
                    'description': f'Угол камеры (по умолчанию {DEFAULT_ANGLE})',
                },
                'images_data[][height]': {
                    'type': 'number',
                    'format': 'float',
                    'description': f'Высота камеры (по умолчанию {DEFAULT_HEIGHT})',
                },
            },
            # 'required': ['images_data[][image]'], # Это не работает так в multipart/form-data
        }
    },
    responses={
        200: OpenApiResponse(
            description="Изображения успешно загружены и обработаны",
            response=upload_success_response_schema
        ),
        400: OpenApiResponse(
            description="Ошибка валидации файлов",
            response=upload_validation_error_schema
        ),
        500: OpenApiResponse(
            description="Ошибка загрузки или внутренняя ошибка сервера",
            response=upload_server_error_schema
        )
    },
    examples=[
        OpenApiExample(
            name="Успешный запрос",
            value={},
            response_only=True,
            status_codes=["200"]
        ),
        OpenApiExample(
            name="Ошибка валидации",
            value={
                "validation_errors": [
                    {
                        "file_index": 0,
                        "filename": "photo.jpg",
                        "error": "Empty or missing file"
                    }
                ]
            },
            response_only=True,
            status_codes=["400"]
        ),
        OpenApiExample(
            name="Серверная ошибка",
            value={
                "error": "Upload failed",
                "details": "Server error occurred during file upload"
            },
            response_only=True,
            status_codes=["500"]
        )
    ],
    summary="Загрузка изображений и создание задач на обработку",
    description="Принимает массив изображений и связанных с ними данных (адрес, координаты, угол, высота). "
                "Если предоставлен только адрес, производится геокодирование для получения координат. "
                "Если предоставлены только координаты, производится обратное геокодирование для получения адреса. "
                "Затем изображения валидируются, загружаются в S3, и создаются задачи для асинхронной обработки.",
)
class UploadImageView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        raw = request.data
        files = request.FILES

        images_data = []
        i = 0
        while f"images_data[{i}][image]" in raw or f"images_data[{i}][address]" in raw:
            images_data.append({
                "image": files.get(f"images_data[{i}][image]"),
                "address": raw.get(f"images_data[{i}][address]"),
                "lat": raw.get(f"images_data[{i}][lat]"),
                "lon": raw.get(f"images_data[{i}][lon]"),
                "angle": raw.get(f"images_data[{i}][angle]", DEFAULT_ANGLE),
                "height": raw.get(f"images_data[{i}][height]", DEFAULT_HEIGHT),
            })
            i += 1

        serializer = ImageDataSerializer(data=images_data, many=True)
        serializer.is_valid(raise_exception=True)
        geolocator = Nominatim(user_agent="my_app")
        images_data = serializer.validated_data
        processed = []
        for item in images_data:
            image = item["image"]
            address = item.get("address")
            lat = item.get("lat")
            lon = item.get("lon")

            # Если есть адрес, но нет координат → геокодируем
            if address and (lat is None or lon is None):
                try:
                    loc = geolocator.geocode(address)
                    if loc:
                        lat, lon = loc.latitude, loc.longitude
                except Exception as e:
                    print(f" Ошибка геокодирования {address}: {e}")

            # Если есть координаты, но нет адреса → обратное геокодирование
            if (lat is not None and lon is not None) and not address:
                try:
                    loc = geolocator.reverse((lat, lon))
                    if loc:
                        address = loc.address
                except Exception as e:
                    print(f"Ошибка reverse для {lat}, {lon}: {e}")

            processed.append({
                "image": image,
                "address": address,
                "lat": lat,
                "lon": lon,
                "angle": item.get("angle"),
                "height": item.get("height"),
            })

        service = ImageUploadService(request.user)
        validated_files, validation_errors = service.validate_files(processed)
        if validation_errors:
            return Response({"validation_errors": validation_errors}, status=status.HTTP_400_BAD_REQUEST)

        uploaded_images, errors = service.upload_and_process(validated_files)

        if errors:
            return Response({"error": "Upload failed", "details": errors}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({}, status=status.HTTP_200_OK)

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


# --- UploadArchiveView ---
# Схема успешного ответа
upload_archive_success_response_schema = {
    "type": "object",
    "properties": {
        "message": {"type": "string"},
        "archive_id": {"type": "integer"}
    },
    "required": ["message", "archive_id"]
}

# Схема ошибки 400
upload_archive_error_400_schema = {
    "type": "object",
    "properties": {
        "error": {"type": "string"}
    },
    "required": ["error"]
}

# Схема ошибки 500
upload_archive_error_500_schema = {
    "type": "object",
    "properties": {
        "error": {"type": "string"}
    },
    "required": ["error"]
}

@extend_schema(
    request={
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'archive': {
                    'type': 'string',
                    'format': 'binary',
                    'description': 'ZIP-архив с изображениями',
                },
            },
            'required': ['archive'],
        }
    },
    responses={
        202: OpenApiResponse(
            description="Архив успешно загружен, задача на обработку поставлена в очередь",
            response=upload_archive_success_response_schema
        ),
        400: OpenApiResponse(
            description="Архив не предоставлен",
            response=upload_archive_error_400_schema
        ),
        500: OpenApiResponse(
            description="Ошибка загрузки или внутренняя ошибка сервера",
            response=upload_archive_error_500_schema
        )
    },
    examples=[
        OpenApiExample(
            name="Успешный запрос",
            value={"message": "Archive uploaded", "archive_id": 123},
            response_only=True,
            status_codes=["202"]
        ),
        OpenApiExample(
            name="Ошибка 400",
            value={"error": "No archive uploaded"},
            response_only=True,
            status_codes=["400"]
        ),
        OpenApiExample(
            name="Ошибка 500",
            value={"error": "Failed to process archive"},
            response_only=True,
            status_codes=["500"]
        )
    ],
    summary="Загрузка архива с изображениями",
    description="Принимает ZIP-архив, содержащий изображения. "
                "Архив загружается в S3, и создается асинхронная задача для его обработки. "
                "Обработка может включать извлечение изображений, их валидацию и последующую "
                "загрузку в систему с созданием соответствующих задач.",
)
class UploadArchiveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        archive_file = request.FILES.get("archive")
        metadata_file = request.FILES.get("json")  # необязательное поле

        if not archive_file:
            return Response({"error": "No archive uploaded"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            service = ArchiveUploadService(request.user)
            archive = service.upload_archive(archive_file, metadata_file)
            return Response({"message": "Archive uploaded", "archive_id": archive.id}, status=status.HTTP_202_ACCEPTED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# --- GetUserImageLocationsView ---
# Схема ответа для одного элемента results
image_location_item_schema = {
    "type": "object",
    "properties": {
        'id': {"type": "integer", "example": 1},
        'status': {"type": "string", "example": 'done'},
        'created_at': {"type": "string", "format": "date-time", "example": '2023-10-20T10:00:00Z'},
        'user': {
            "type": "object",
            "properties": {
                'id': {"type": "integer", "example": 1},
                'username': {"type": "string", "example": 'john_doe'},
            }
        },
        'main_address': {"type": "string", "example": 'ул. Пушкина, д. 10, г. Москва'},
        'main_coordinates': {
            "type": "object",
            "properties": {
                'lat': {"type": "number", "format": "float", "example": 55.7558},
                'lon': {"type": "number", "format": "float", "example": 37.6173}
            },
            "nullable": True
        },
        'main_image': {
            "type": "object",
            "properties": {
                'id': {"type": "integer", "example": 1},
                'filename': {"type": "string", "example": 'image.jpg'},
                'file_path': {"type": "string", "example": '/path/to/image.jpg'},
                'preview_url': {"type": "string", "format": "uri", "example": 'http://example.com/preview.jpg'},
            }
        },
        'trash_images': {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    'id': {"type": "integer", "example": 1},
                    'image': {
                        "type": "object",
                        "properties": {
                            'id': {"type": "integer", "example": 2},
                            'filename': {"type": "string", "example": 'trash.jpg'},
                            # ... другие поля изображения ...
                        }
                    },
                    'lat': {"type": "number", "format": "float", "example": 55.7568},
                    'lon': {"type": "number", "format": "float", "example": 37.6183},
                }
            }
        }
    }
}

# Схема ответа с пагинацией
get_user_locations_response_schema = {
    "type": "object",
    "properties": {
        'count': {"type": "integer", "example": 100},
        'next': {"type": "string", "format": "uri", "nullable": True, "example": 'http://api.example.org/accounts/?page=2'},
        'previous': {"type": "string", "format": "uri", "nullable": True, "example": 'http://api.example.org/accounts/?page=1'},
        'results': {
            "type": "array",
            "items": image_location_item_schema
        }
    }
}

# Схема ошибки 401
auth_error_schema = {
    "type": "object",
    "properties": {
        "error": {"type": "string"}
    },
    "required": ["error"]
}

@extend_schema(
    request=None, # GET-запрос не имеет тела
    responses={
        200: OpenApiResponse(
            description="Список локаций успешно получен",
            response=get_user_locations_response_schema
        ),
        401: OpenApiResponse(
            description="Требуется аутентификация",
            response=auth_error_schema
        )
    },
    parameters=[
        # Query parameters
        # openapi.Parameter не используется напрямую, но можно описать через параметры
        # или через фильтры, если они интегрированы
        # Здесь описываем параметры вручную
    ],
    examples=[
        OpenApiExample(
            name="Успешный ответ",
            value={
                "count": 1,
                "next": None,
                "previous": None,
                "results": [
                    image_location_item_schema["properties"] # example value
                ]
            },
            response_only=True,
            status_codes=["200"]
        ),
        OpenApiExample(
            name="Ошибка 401",
            value={"error": "Authentication required"},
            response_only=True,
            status_codes=["401"]
        )
    ],
    summary="Получить список локаций изображений пользователя",
    description="Возвращает список локаций изображений, принадлежащих аутентифицированному пользователю. "
                "Поддерживает фильтрацию по дате создания и по радиусу от заданной точки, "
                "а также пагинацию результатов.",
    # Документация для query параметров не включена в extend_schema напрямую
    # Она будет автоматически сгенерирована из фильтров, если они настроены
)
class GetUserImageLocationsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user

        if not user.is_authenticated:
            return Response(
                {"error": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Базовый QuerySet, ограниченный пользователем
        base_queryset = ImageLocation.objects.filter(user=user).select_related('image', 'user').order_by('-id')

        # Инициализируем оба фильтра с одинаковым QuerySet
        # 1. Фильтр по дате
        date_filter_instance = ImageLocationDateFilter(request.query_params, queryset=base_queryset)
        # 2. Фильтр по радиусу
        radius_filter_instance = RadiusFilter(request.query_params, queryset=date_filter_instance.qs)

        # Применяем оба фильтра последовательно
        final_queryset = radius_filter_instance.qs

        # Пагинация
        paginator = CustomPagination()
        paginated_locations = paginator.paginate_queryset(final_queryset, request)

        # Формируем список словарей через to_dict()
        response_data = [loc.to_dict() for loc in paginated_locations]

        # Возвращаем ответ с пагинацией
        return paginator.get_paginated_response(response_data)


# --- DeleteUserImageLocationView ---
# Схема успешного ответа
delete_success_response_schema = {
    "type": "object",
    "properties": {
        "message": {"type": "string"}
    },
    "required": ["message"]
}

# Схема ошибки 404
delete_error_404_schema = {
    "type": "object",
    "properties": {
        "error": {"type": "string"}
    },
    "required": ["error"]
}

@extend_schema(
    request=None, # DELETE-запрос не имеет тела
    responses={
        200: OpenApiResponse(
            description="Локация успешно удалена",
            response=delete_success_response_schema
        ),
        404: OpenApiResponse(
            description="Локация не найдена или не принадлежит пользователю",
            response=delete_error_404_schema
        )
    },
    examples=[
        OpenApiExample(
            name="Успешный запрос",
            value={"message": "ImageLocation 123 deleted"},
            response_only=True,
            status_codes=["200"]
        ),
        OpenApiExample(
            name="Ошибка 404",
            value={"error": "ImageLocation not found"},
            response_only=True,
            status_codes=["404"]
        )
    ],
    summary="Удалить конкретную локацию изображения пользователя",
    description="Удаляет локацию изображения, принадлежащую аутентифицированному пользователю, "
                "по её уникальному идентификатору. "
                "Удаление каскадно затрагивает связанные объекты (например, DetectedImageLocation).",
)
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


detected_location_item_schema = {
    "type": "object",
    "properties": {
        'id': {"type": "integer", "example": 1},
        'file': {
            "type": "object",
            "properties": {
                'id': {"type": "integer", "example": 1},
                'filename': {"type": "string", "example": 'trash_image.jpg'},
                'original_filename': {"type": "string", "example": 'original_trash.jpg'},
                'file_path': {"type": "string", "example": '/path/to/trash_image.jpg'},
                's3_url': {"type": "string", "format": "uri", "example": 'http://s3.example.com/trash_image.jpg'},
                'preview_url': {"type": "string", "format": "uri", "example": 'http://example.com/preview.jpg'},
                'uploaded_at': {"type": "string", "format": "date-time", "example": '2023-10-20T10:00:00Z'},
            }
        },
        'image_location_id': {"type": "integer", "example": 123},
        'lat': {"type": "number", "format": "float", "example": 55.7568},
        'lon': {"type": "number", "format": "float", "example": 37.6183},
        'created_at': {"type": "string", "format": "date-time", "example": '2023-10-20T11:00:00Z'},
        'address': {"type": "string", "example": 'ул. Ленина, д. 15, г. Москва'},
    }
}

# Схема ответа с оберткой "data"
get_user_detected_locations_response_schema = {
    "type": "object",
    "properties": {
        'data': {
            "type": "array",
            "items": detected_location_item_schema
        }
    }
}

@extend_schema(
    parameters=[ # Документация для query параметров
        OpenApiParameter(
            name="latitude",
            type=float,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Широта центральной точки для фильтрации по радиусу"
        ),
        OpenApiParameter(
            name="longitude",
            type=float,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Долгота центральной точки для фильтрации по радиусу"
        ),
    ],
    request=None, # GET-запрос не имеет тела
    responses={
        200: OpenApiResponse(
            description="Список обнаруженных локаций успешно получен",
            response=get_user_detected_locations_response_schema
        ),
        401: OpenApiResponse(
            description="Требуется аутентификация",
            response=auth_error_schema
        )
    },
    examples=[
        OpenApiExample(
            name="Успешный ответ",
            value={
                "data": [ # Используем "data", как в схеме и в ответе view
                    {
                        "id": 1,
                        "file": {
                            "id": 1,
                            "filename": "trash_image.jpg",
                            "original_filename": "original_trash.jpg",
                            "file_path": "/path/to/trash_image.jpg",
                            "s3_url": "http://s3.example.com/trash_image.jpg",
                            "preview_url": "http://example.com/preview.jpg",
                            "uploaded_at": "2023-10-20T10:00:00Z",
                        },
                        "image_location_id": 123,
                        "lat": 55.7568,
                        "lon": 37.6183,
                        "created_at": "2023-10-20T11:00:00Z",
                        "address": "ул. Ленина, д. 15, г. Москва"
                    }
                ]
            },
            response_only=True,
            status_codes=["200"]
        ),
        OpenApiExample(
            name="Ошибка 401",
            value={"error": "Authentication required"},
            response_only=True,
            status_codes=["401"]
        )
    ],
    summary="Получить список обнаруженных локаций мусора пользователя",
    description="Возвращает список обнаруженных локаций мусора (DetectedImageLocation), "
                "связанных с изображениями, загруженными аутентифицированным пользователем. "
                "Поддерживает фильтрацию по радиусу от заданной точки. "
                "Ответ оборачивается в ключ 'data'.",
)
class GetUserDetectedLocation(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user

        if not user.is_authenticated:
            return Response(
                {"error": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        base_queryset = DetectedImageLocation.objects.filter(
            file__user=user
        ).select_related('file', 'image_location', 'file__user').order_by('-id')

        radius_filter_instance = RadiusFilter(request.query_params, queryset=base_queryset)
        final_queryset = radius_filter_instance.qs

        response_data = [loc.to_dict() for loc in final_queryset]

        # оборачиваем под ключ "data"
        return Response({"data": response_data}, status=status.HTTP_200_OK)
    

@extend_schema(
    request=None,  # POST-запрос не требует тела, только pk в URL
    responses={
        200: OpenApiResponse(
            description="Задача на повторную обработку успешно отправлена",
            response={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "example": "ImageLocation 42 retried"}
                }
            }
        ),
        401: OpenApiResponse(
            description="Требуется аутентификация",
            response={"type": "object", "properties": {"error": {"type": "string"}}}
        ),
        404: OpenApiResponse(
            description="ImageLocation не найден у текущего пользователя",
            response={"type": "object", "properties": {"error": {"type": "string"}}}
        ),
    },
    examples=[
        OpenApiExample(
            name="Успешный ответ",
            value={"message": "ImageLocation 42 retried"},
            response_only=True,
            status_codes=["200"]
        ),
        OpenApiExample(
            name="Ошибка 401",
            value={"error": "Authentication required"},
            response_only=True,
            status_codes=["401"]
        ),
        OpenApiExample(
            name="Ошибка 404",
            value={"error": "ImageLocation not found"},
            response_only=True,
            status_codes=["404"]
        ),
    ],
    summary="Повторная обработка ImageLocation",
    description=(
        "Позволяет пользователю повторно отправить на обработку конкретный объект `ImageLocation`. "
        "Перед повторной отправкой все связанные `DetectedImageLocation` удаляются, "
        "а статус `ImageLocation` переводится в `processing` (ожидает). "
        "После этого задача снова ставится в очередь Celery."
    ),
)
class RetryUserImageLocationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        user = request.user

        try:
            # Ищем объект только у текущего пользователя
            image_location = ImageLocation.objects.get(id=pk, user=user)
        except ImageLocation.DoesNotExist:
            return Response(
                {"error": "ImageLocation not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        service = ImageUploadService(request.user)
        service.retry_result(image_location)

        return Response({"message": f"ImageLocation {pk} retried"}, status=status.HTTP_200_OK)