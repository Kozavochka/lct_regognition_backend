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

    def upload_archive(self, file_obj):
        """
        Загружает архив в S3 и создаёт запись в БД
        """
        filename = f"archives/{uuid.uuid4()}_{file_obj.name}"
        file_content = file_obj.read()

        success = self.s3_service.upload_file(filename, file_content, content_type="application/zip")
        if not success:
            raise Exception("Failed to upload archive to S3")

        s3_url = self.s3_service.generate_file_url(filename)

        archive = UploadedArchive.objects.create(
            filename=filename,
            original_filename=file_obj.name,
            s3_url=s3_url,
            user=self.user
        )

        # ставим задачу в очередь
        process_archive_task.delay(archive.id)

        return archive
