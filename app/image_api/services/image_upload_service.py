import uuid
import logging
from django.db import transaction
from image_api.models import UploadedImage, ImageLocation
from image_api.services.s3_service import S3Service

logger = logging.getLogger(__name__)

class ImageUploadService:
    def __init__(self, user):
        self.user = user
        self.s3_service = S3Service()

    def validate_files(self, processed):
        validated_files = []
        validation_errors = []

        for i, item in enumerate(processed):
            file_obj = item.get("image")
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
                    "filename": filename,
                    "content": file_content,
                    "original_filename": file_obj.name,
                    "index": i,
                    "content_type": getattr(file_obj, "content_type", "application/octet-stream"),
                    "address": item.get("address"),
                    "lat": item.get("lat"),
                    "lon": item.get("lon"),
                    "angle": item.get("angle"),
                    "height": item.get("height"),
                })
            except Exception as e:
                validation_errors.append({
                    "file_index": i,
                    "filename": getattr(file_obj, "name", f"file_{i}"),
                    "error": str(e)
                })

        return validated_files, validation_errors

    @transaction.atomic
    def upload_and_process(self, validated_files):
        from image_api.tasks import process_geo_tasks
        uploaded_images = []
        upload_errors = []

        upload_results = self.s3_service.batch_upload(validated_files)

        for success_file in upload_results['successful']:
            try:
                uploaded = UploadedImage.objects.create(
                    filename=success_file['filename'],
                    original_filename=success_file['original_filename'],
                    file_path=f"uploads/{success_file['filename']}",
                    s3_url=success_file['url'],
                    user=self.user
                )
                uploaded_images.append(uploaded)
                logger.info(f"Database record created: {success_file['filename']}")
            except Exception as db_error:
                logger.error(f"Database error for {success_file['filename']}: {str(db_error)}")
                self.s3_service.delete_file(success_file['filename'])
                upload_errors.append({
                    "file_index": success_file['index'],
                    "filename": success_file['original_filename'],
                    "error": f"Database error: {str(db_error)}"
                })

        upload_errors.extend(upload_results['failed'])

        if upload_errors:
            self._rollback(uploaded_images)
            return None, upload_errors

        # Создаём ImageLocation
        image_locations = []
        for uploaded_image in uploaded_images:
            location = ImageLocation.objects.create(
                user=self.user,
                image=uploaded_image,
                status='processing'
            )
            image_locations.append(location)

        # Отправляем в Celery
        images_data = [
            {
                "task_id": loc.id,                       
                "image_filename": loc.image.filename,
                "angle": loc.angle,
                "height": loc.height,
                "lat": loc.lat,
                "lon": loc.lon,
            }
            for loc in image_locations
        ]
        process_geo_tasks.delay(images_data)

        return uploaded_images, None

    def _rollback(self, uploaded_images):
        for uploaded_image in uploaded_images:
            try:
                uploaded_image.delete()
                self.s3_service.delete_file(uploaded_image.filename)
            except Exception as e:
                logger.error(f"Rollback error for {uploaded_image.filename}: {str(e)}")
