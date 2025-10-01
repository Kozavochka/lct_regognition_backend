from celery import shared_task
from .models import ImageLocation
from .utils import _send_geo_request_internal  # внутренняя версия _send_geo_request
from django.core.exceptions import ObjectDoesNotExist
import logging

logger = logging.getLogger(__name__)

@shared_task
def process_geo_tasks(images_data):
    """
    Асинхронная задача для отправки запроса на геолокацию.
    """
    geo_result = _send_geo_request_internal(images_data)

    if geo_result:
        for error in geo_result['errors']:
            task_id = error['task_id']
            try:
                location = ImageLocation.objects.get(image__id=int(task_id))
                location.status = 'failed'
                location.save()
                logger.info(f"Updated ImageLocation {location.id} to 'failed'")
            except ImageLocation.DoesNotExist:
                logger.warning(f"ImageLocation not found for task_id={task_id}")
    else:
        logger.error("Geo request failed with no result returned.")