import json
import os

from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from recognition_backend.settings import AWS_S3_ENDPOINT_URL
from .models import ImageLocation, UploadedImage, DetectedImageLocation
from geopy.geocoders import Nominatim

from .services.s3_service import S3Service


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
            if latitude is not None and image_location.lat is not None:
                image_location.lat = latitude
            if longitude is not None and image_location.lon is not None:
                image_location.lon = longitude

            if address is not None:
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

@api_view(['POST'])
@permission_classes([AllowAny])
def image_trash_result_callback(request):
    response_data = request.data

    task_id = response_data.get("TaskId")
    status_response = response_data.get("Status")
    result_array = response_data.get("Result", [])

    if status_response != "Succeeded":
        error_msg = f"Задача завершилась со статусом {status_response}. Ошибка: {response_data.get('ErrorMessage')}"
        print(error_msg)
        return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)

    try:
        image_location = ImageLocation.objects.get(id=task_id)
        user = image_location.user
    except ImageLocation.DoesNotExist:
        error_msg = f"ImageLocation с id {task_id} не найден."
        print(error_msg)
        return Response({"error": error_msg}, status=status.HTTP_404_NOT_FOUND)

    s3 = S3Service()

    processed_count = 0
    for item in result_array:
        image_path = item.get("ImagePath")
        latitude = item.get("Latitude")
        longitude = item.get("Longitude")

        if not image_path or latitude is None or longitude is None:
            print(f"Пропускаем элемент в Result из-за отсутствия данных: {item}")
            continue

        # try:
        #     obj = s3.s3_client.get_object(Bucket=s3.bucket_name, Key=image_path)
        #     file_content = obj['Body'].read()
        # except Exception as e:
        #     print(f"Ошибка при скачивании файла {image_path} из S3: {e}")
        #     continue

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

        DetectedImageLocation.objects.create(
            file=uploaded_image,
            image_location=image_location,
            lat=latitude,
            lon=longitude
        )
        processed_count += 1
        print(f"Создан DetectedImageLocation для TaskId {task_id}")

    return Response({"message": f"Успешно обработано {processed_count} элементов.", "task_id": task_id},
                    status=status.HTTP_200_OK)
