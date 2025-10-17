import json

from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from .models import ImageLocation
from geopy.geocoders import Nominatim


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