import uuid
import logging

from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import UploadedImage, ImageLocation
from .pagination import CustomPagination
from .services.s3_service import S3Service
from .tasks import process_geo_tasks


logger = logging.getLogger(__name__)

upload_request_schema = {
    "type": "object",
    "properties": {
        "image": {
            "type": "array",
            "items": {
                "type": "string",
                "format": "binary"
            },
            "description": "Массив файлов изображений"
        }
    },
    "required": ["image"],
    "additionalProperties": False
}

# Схема успешного ответа (пустой объект)
success_response_schema = {
    "type": "object",
    "properties": {},
    "additionalProperties": False
}

# Схема ошибки валидации
validation_error_schema = {
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
server_error_schema = {
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
                'image': {
                    'type': 'array',
                    'items': {
                        'type': 'string',
                        'format': 'binary'
                    },
                    'description': 'Массив файлов изображений',
                    'example': ['file1.jpg', 'file2.png']
                }
            },
            'required': ['image'],
            'additionalProperties': False
        }
    },
    responses={
        200: OpenApiResponse(
            description="Успешная загрузка. Нет тела ответа.",
            response=None  # Пустой ответ
        ),
        400: OpenApiResponse(
            description="Ошибка валидации файлов",
            response={
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
        ),
        500: OpenApiResponse(
            description="Серверная ошибка",
            response={
                "type": "object",
                "properties": {
                    "error": {"type": "string"},
                    "details": {"type": "string"}
                },
                "required": ["error", "details"]
            }
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
    summary="Загрузка изображений",
    description=(
        "Загружает одно или несколько изображений. "
        "Файлы сохраняются в S3, создаётся запись в БД и запускается задача на определение геолокации. "
        "В случае ошибки — возвращается список ошибок или общая ошибка сервера."
    )
)
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

            process_geo_tasks.delay(images_data)

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



@extend_schema(
    summary="Получить локации изображений пользователя",
    description=(
        "Возвращает список геолокаций изображений текущего пользователя. "
        "**Доступ только для суперпользователей или пользователей из группы 'Admins'.**"
    ),
    # security=[{"BearerAuth": []}],  # Показывает, что нужна авторизация
    responses={
        200: {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "next": {"type": "string", "nullable": True},
                "previous": {"type": "string", "nullable": True},
                "results": {
                    "type": "array",
                    "items": {
                        "$ref": "#/components/schemas/ImageLocation"
                    }
                }
            },
            "required": ["count", "results"]
        },
        401: OpenApiResponse(description="Неавторизованный доступ"),
        403: OpenApiResponse(
            description="Доступ запрещён. Только суперпользователи или админы.",
            response={
                "type": "object",
                "properties": {
                    "error": {"type": "string"}
                },
                "example": {"error": "Only superusers or admins are allowed"}
            }
        )
    },
    examples=[
        OpenApiExample(
            name="Успешный ответ",
            value={
                "count": 2,
                "next": "http://localhost:8000/api/user-image-locations/?page=2",
                "previous": None,
                "results": [
                    {
                        "id": 1,
                        "status": "done",
                        "lat": 55.7558,
                        "lon": 37.6176,
                        "created_at": "2024-01-01T12:00:00Z",
                        "user": {"id": 1, "username": "admin"},
                        "image": {
                            "id": 1,
                            "filename": "uuid_123.jpg",
                            "file_path": "https://s3.example.com/uploads/uuid_123.jpg"
                        }
                    }
                ]
            },
            response_only=True,
            status_codes=["200"]
        ),
        OpenApiExample(
            name="Ошибка доступа",
            value={"error": "Only superusers or admins are allowed"},
            response_only=True,
            status_codes=["403"]
        )
    ]
)
class GetUserImageLocationsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # Проверяем, является ли пользователь суперпользователем или админом
        if not (request.user.is_superuser or request.user.groups.filter(name='Admins').exists()):
            return Response(
                {"error": "Only superusers or admins are allowed"},
                status=status.HTTP_403_FORBIDDEN
            )

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