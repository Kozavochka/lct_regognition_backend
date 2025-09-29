import json

from django.http import JsonResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import ImageLocation

@api_view(['POST'])
def image_location_callback(request):
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
    address = result.get("Address")

    try:
        # Находим запись по TaskId (предполагается, что TaskId == ImageLocation.id)
        image_location = ImageLocation.objects.get(id=task_id)

        # Обновляем статус в зависимости от ответа
        if status_response == "Succeeded":
            image_location.status = "done"
        elif status_response == "Failed":
            image_location.status = "failed"
            # Можно добавить сохранение ошибки, если нужно:
            # image_location.error_message = error_message
        # Можно добавить другие статусы, если нужно

        # Обновляем координаты и адрес, если статус успешный
        if status_response == "Succeeded":
            image_location.lat = latitude
            image_location.lon = longitude
            if address is not None:
                image_location.address = address

        image_location.save()

        return JsonResponse({
            "status": "success",
            "message": f"Updated record {task_id}",
            "new_status": image_location.status
        })

    except ImageLocation.DoesNotExist:
        return JsonResponse({"error": f"ImageLocation with id={task_id} not found"}, status=404)