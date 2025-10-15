from celery import shared_task
from .models import ImageLocation
from .utils import _send_geo_request_internal  # внутренняя версия _send_geo_request
from django.core.exceptions import ObjectDoesNotExist
import logging
from image_api.models import UploadedArchive
from image_api.services.image_upload_service import ImageUploadService
from image_api.services.s3_service import S3Service
import zipfile
import io
import uuid

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
                location = ImageLocation.objects.get(id=int(task_id))
                location.status = 'failed'
                location.save()
                logger.info(f"Updated ImageLocation {location.id} to 'failed'")
            except ImageLocation.DoesNotExist:
                logger.warning(f"ImageLocation not found for task_id={task_id}")
    else:
        logger.error("Geo request failed with no result returned.")

@shared_task
def process_archive_task(archive_id):
    try:
        archive = UploadedArchive.objects.get(id=archive_id)
        logger.info(f"Processing archive {archive.filename}")

        s3 = S3Service()

        # Скачиваем файл из S3 в память
        obj = s3.s3_client.get_object(Bucket=s3.bucket_name, Key=archive.filename)
        file_bytes = obj["Body"].read()

        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            image_files = [f for f in zf.namelist() if not f.endswith("/")]

            validated_files = []
            for i, name in enumerate(image_files):
                with zf.open(name) as file_data:
                    content = file_data.read()
                    # простая проверка по расширению
                    if not name.lower().endswith((".jpg", ".jpeg", ".png", ".gif")):
                        logger.warning(f"Skipped non-image file: {name}")
                        continue

                    validated_files.append({
                        "filename": f"{uuid.uuid4()}_{name}",
                        "content": content,
                        "original_filename": name,
                        "index": i,
                        "content_type": "image/jpeg" if name.lower().endswith("jpg") else "image/png"
                    })

            if validated_files:
                service = ImageUploadService(archive.user)
                service.upload_and_process(validated_files)

    except Exception as e:
        logger.error(f"Error processing archive {archive_id}: {str(e)}")        