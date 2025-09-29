from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import ImageLocation

@api_view(['POST'])
def image_location_callback(request):
    task_id = request.data.get('taskId')
    lat = request.data.get('lat')
    lon = request.data.get('lon')

    if not task_id or lat is None or lon is None:
        return Response(
            {"error": "taskId, lat, lon обязательны."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        instance = get_object_or_404(ImageLocation, id=task_id)
        instance.lat = lat
        instance.lon = lon
        instance.status = 'done'
        instance.save(update_fields=['lat', 'lon', 'status'])
        return Response({"status": "updated"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)