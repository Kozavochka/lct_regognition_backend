import json
import os

from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from drf_spectacular.openapi import OpenApiTypes

from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import ImageLocation, UploadedImage, DetectedImageLocation
from geopy.geocoders import Nominatim

from .services.s3_service import S3Service


# --- image_location_callback ---
# Схема запроса
callback_request_schema = {
    "type": "object",
    "properties": {
        "TaskId": {"type": "string", "description": "ID задачи (идентифицирует запись ImageLocation)"},
        "Status": {"type": "string", "enum": ["Succeeded", "Failed"], "description": "Статус выполнения задачи"},
        "ErrorCode": {"type": "string", "description": "Код ошибки (если была ошибка)"},
        "ErrorMessage": {"type": "string", "description": "Сообщение об ошибке (если была ошибка)"},
        "Result": {
            "type": "object",
            "properties": {
                "Latitude": {"type": "number", "format": "float", "description": "Широта"},
                "Longitude": {"type": "number", "format": "float", "description": "Долгота"}
            },
            "description": "Результат обработки (если успешно)"
        }
    },
    "required": ["TaskId", "Status"]
}

# Схема успешного ответа
callback_success_response_schema = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "example": "success"},
        "message": {"type": "string", "example": "Updated record 123"},
        "new_status": {"type": "string", "example": "done"}
    }
}

# Схема ошибки 400
callback_error_400_schema = {
    "type": "object",
    "properties": {
        "error": {"type": "string", "example": "Invalid JSON"}
    }
}

# Схема ошибки 404
callback_error_404_schema = {
    "type": "object",
    "properties": {
        "error": {"type": "string", "example": "ImageLocation with id=123 not found"}
    }
}

# Схема ошибки 500
callback_error_500_schema = {
    "type": "object",
    "properties": {
        "error": {"type": "string", "example": "An error occurred: ..."}
    }
}

@extend_schema(
    request=callback_request_schema,
    responses={
        200: OpenApiResponse(
            description="Статус успешно обновлен",
            response=callback_success_response_schema
        ),
        400: OpenApiResponse(
            description="Некорректный JSON",
            response=callback_error_400_schema
        ),
        404: OpenApiResponse(
            description="Запись ImageLocation не найдена",
            response=callback_error_404_schema
        ),
        500: OpenApiResponse(
            description="Внутренняя ошибка сервера",
            response=callback_error_500_schema
        )
    },
    examples=[
        OpenApiExample(
            name="Успешный запрос",
            value={
                "TaskId": "123",
                "Status": "Succeeded",
                "Result": {
                    "Latitude": 55.7558,
                    "Longitude": 37.6173
                }
            },
            request_only=True
        ),
        OpenApiExample(
            name="Успешный ответ",
            value={
                "status": "success",
                "message": "Updated record 123",
                "new_status": "done"
            },
            response_only=True,
            status_codes=["200"]
        ),
        OpenApiExample(
            name="Ошибка 400",
            value={"error": "Invalid JSON"},
            response_only=True,
            status_codes=["400"]
        ),
        OpenApiExample(
            name="Ошибка 404",
            value={"error": "ImageLocation with id=123 not found"},
            response_only=True,
            status_codes=["404"]
        ),
        OpenApiExample(
            name="Ошибка 500",
            value={"error": "An error occurred: Something went wrong"},
            response_only=True,
            status_codes=["500"]
        )
    ],
    summary="Callback для обновления статуса локации изображения",
    description="Этот эндпоинт используется для получения обратного вызова от внешней службы "
                "по обработке изображений и обновления статуса и координат соответствующей "
                "записи ImageLocation.",
)
@api_view(['POST'])
@permission_classes([AllowAny])
def image_location_callback(request):
    print("Request body:", request.body.decode('utf-8'))

    geolocator = Nominatim(user_agent="my_app")
    try:
        # Получаем JSON из тела запроса
        json_data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    # Извлекаем TaskId и результат
    task_id = json_data.get("TaskId")
    status_response = json_data.get("Status")
    error_code = json_data.get("ErrorCode")
    error_message = json_data.get("ErrorMessage")
    result = json_data.get("Result", {})

    latitude = result.get("Latitude")
    longitude = result.get("Longitude")

    try:
        image_location = ImageLocation.objects.get(id=task_id)
        address = image_location.address
        # Обновляем статус в зависимости от ответа
        if status_response == "Succeeded":
            image_location.status = "done"
        elif status_response == "Failed":
            image_location.status = "failed"

        # Обновляем координаты и адрес, если статус успешный
        if status_response == "Succeeded":
            if latitude is not None and image_location.lat is None:
                image_location.lat = latitude
            if longitude is not None and image_location.lon is None:
                image_location.lon = longitude

            if address is None:
                try:
                    loc = geolocator.reverse((latitude, longitude))
                    if loc:
                        address = loc.address
                except Exception as e:
                    print(f"Ошибка reverse для {latitude}, {longitude}: {e}")

        image_location.address = address
        image_location.save()

        return JsonResponse({
            "status": "success",
            "message": f"Updated record {task_id}",
            "new_status": image_location.status
        })

    except ImageLocation.DoesNotExist:
        return JsonResponse({"error": f"ImageLocation with id={task_id} not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": f"An error occurred: {str(e)}"}, status=500)


# --- image_trash_result_callback ---
# Схема запроса
trash_callback_request_schema = {
    "type": "object",
    "properties": {
        "TaskId": {"type": "string", "description": "ID задачи (идентифицирует запись ImageLocation)"},
        "Status": {"type": "string", "enum": ["Succeeded", "Failed"], "description": "Статус выполнения задачи"},
        "ErrorCode": {"type": "string", "description": "Код ошибки (если была ошибка)"},
        "ErrorMessage": {"type": "string", "description": "Сообщение об ошибке (если была ошибка)"},
        "Result": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ImagePath": {"type": "string", "description": "Путь к изображению с обнаруженным объектом"},
                    "Latitude": {"type": "number", "format": "float", "description": "Широта точки обнаружения"},
                    "Longitude": {"type": "number", "format": "float", "description": "Долгота точки обнаружения"}
                },
                "required": ["ImagePath", "Latitude", "Longitude"]
            },
            "description": "Массив результатов обработки"
        }
    },
    "required": ["TaskId", "Status"]
}

# Схема успешного ответа
trash_callback_success_response_schema = {
    "type": "object",
    "properties": {
        "message": {"type": "string", "example": "Успешно обработано 3 элементов."},
        "task_id": {"type": "string", "example": "123"}
    }
}

# Схема ошибки 400
trash_callback_error_400_schema = {
    "type": "object",
    "properties": {
        "error": {"type": "string", "example": "Задача завершилась со статусом Failed. Ошибка: Processing error"}
    }
}

# Схема ошибки 404
trash_callback_error_404_schema = {
    "type": "object",
    "properties": {
        "error": {"type": "string", "example": "ImageLocation с id 123 не найден."}
    }
}

@extend_schema(
    request=trash_callback_request_schema,
    responses={
        200: OpenApiResponse(
            description="Результаты успешно обработаны",
            response=trash_callback_success_response_schema
        ),
        400: OpenApiResponse(
            description="Ошибка в данных запроса или статус задачи не Succeeded",
            response=trash_callback_error_400_schema
        ),
        404: OpenApiResponse(
            description="ImageLocation не найден",
            response=trash_callback_error_404_schema
        )
    },
    examples=[
        OpenApiExample(
            name="Успешный запрос",
            value={
                "TaskId": "123",
                "Status": "Succeeded",
                "Result": [
                    {
                        "ImagePath": "/path/to/trash1.jpg",
                        "Latitude": 55.7568,
                        "Longitude": 37.6183
                    },
                    {
                        "ImagePath": "/path/to/trash2.jpg",
                        "Latitude": 55.7578,
                        "Longitude": 37.6193
                    }
                ]
            },
            request_only=True
        ),
        OpenApiExample(
            name="Успешный ответ",
            value={
                "message": "Успешно обработано 2 элементов.",
                "task_id": "123"
            },
            response_only=True,
            status_codes=["200"]
        ),
        OpenApiExample(
            name="Ошибка 400",
            value={"error": "Задача завершилась со статусом Failed. Ошибка: Processing error"},
            response_only=True,
            status_codes=["400"]
        ),
        OpenApiExample(
            name="Ошибка 404",
            value={"error": "ImageLocation с id 123 не найден."},
            response_only=True,
            status_codes=["404"]
        )
    ],
    summary="Callback для обработки результатов поиска мусора на изображении",
    description="Этот эндпоинт принимает результаты обработки изображения, "
                "содержащие координаты обнаруженных объектов (мусора), "
                "создает записи UploadedImage и DetectedImageLocation, "
                "и обновляет связь с исходной задачей ImageLocation.",
)
@api_view(['POST'])
@permission_classes([AllowAny])
def image_trash_result_callback(request):
    response_data = request.data

    task_id = response_data.get("TaskId")
    status_response = response_data.get("Status")
    result_array = response_data.get("Result", [])

    try:
        image_location = ImageLocation.objects.get(id=task_id)
        user = image_location.user
    except ImageLocation.DoesNotExist:
        error_msg = f"ImageLocation с id {task_id} не найден."
        print(error_msg)
        return Response({"error": error_msg}, status=status.HTTP_404_NOT_FOUND)
    
    if status_response != "Succeeded":
        error_msg = f"Задача завершилась со статусом {status_response}. Ошибка: {response_data.get('ErrorMessage')}"
        print(error_msg)
        image_location.status = "failed"
        image_location.error_reason = response_data.get('ErrorMessage')
        image_location.save()
        return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)
    s3 = S3Service()

    processed_count = 0
    geolocator = Nominatim(user_agent="my_app")
    for item in result_array:
        image_path = item.get("ImagePath")
        latitude = item.get("Latitude")
        longitude = item.get("Longitude")

        if not image_path or latitude is None or longitude is None:
            print(f"Пропускаем элемент в Result из-за отсутствия данных: {item}")
            continue

        filename = os.path.basename(image_path)
        original_filename = filename
        file_path = image_path
        s3_url = image_path

        uploaded_image = UploadedImage.objects.create(
            filename=filename,
            original_filename=original_filename,
            file_path=file_path,
            s3_url=s3_url,
            user=user
        )

        address = ""
        try:
            loc = geolocator.reverse((latitude, longitude))
            if loc:
                address = loc.address
        except Exception as e:
            print(f"Ошибка reverse для {latitude}, {longitude}: {e}")

        DetectedImageLocation.objects.create(
            file=uploaded_image,
            image_location=image_location,
            lat=latitude,
            lon=longitude,
            address = address,
        )
        processed_count += 1
        print(f"Создан DetectedImageLocation для TaskId {task_id}")

    image_location.status = "done"
    image_location.save()
    return Response({"message": f"Успешно обработано {processed_count} элементов.", "task_id": task_id},
                    status=status.HTTP_200_OK)
