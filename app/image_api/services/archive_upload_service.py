import uuid
import zipfile
import io
import logging
from django.conf import settings
from .s3_service import S3Service
from image_api.models import UploadedArchive
from image_api.tasks import process_archive_task

logger = logging.getLogger(__name__)

class ArchiveUploadService:
    def __init__(self, user):
        self.user = user
        self.s3_service = S3Service()

    def upload_archive(self, archive_file, metadata_file=None):
        # Загружаем архив
        archive_filename = f"archives/{uuid.uuid4()}_{archive_file.name}"
        archive_content = archive_file.read()

        success = self.s3_service.upload_file(archive_filename, archive_content, content_type="application/zip")
        if not success:
            raise Exception("Failed to upload archive to S3")

        archive_s3_url = self.s3_service.generate_file_url(archive_filename)

        metadata_filename = None
        metadata_s3_url = None

        if metadata_file:
            metadata_filename = f"archives/{uuid.uuid4()}_{metadata_file.name}"
            metadata_content = metadata_file.read()
            success = self.s3_service.upload_file(metadata_filename, metadata_content, content_type="application/json")
            if not success:
                raise Exception("Failed to upload metadata JSON to S3")
            metadata_s3_url = self.s3_service.generate_file_url(metadata_filename)

        archive = UploadedArchive.objects.create(
            filename=archive_filename,
            original_filename=archive_file.name,
            s3_url=archive_s3_url,
            user=self.user,
            metadata_filename=metadata_filename,
            metadata_s3_url=metadata_s3_url
        )

        # Задачу в очередь
        process_archive_task.delay(archive.id)
        return archive
