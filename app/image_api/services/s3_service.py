import os
import logging
import boto3
from botocore.exceptions import ClientError
from typing import List, Dict, Any, Optional

# from app.recognition_backend.settings import AWS_S3_ENDPOINT_URL, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_REGION_NAME

from django.conf import settings

AWS_S3_ENDPOINT_URL = settings.AWS_S3_ENDPOINT_URL
AWS_ACCESS_KEY_ID = settings.AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY = settings.AWS_SECRET_ACCESS_KEY
AWS_S3_REGION_NAME = settings.AWS_S3_REGION_NAME

logger = logging.getLogger(__name__)


class S3Service:
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            endpoint_url=AWS_S3_ENDPOINT_URL,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_S3_REGION_NAME,
        )
        self.bucket_name = os.getenv('AWS_STORAGE_BUCKET_NAME')

    def upload_file(self, filename: str, content: bytes, content_type: str = 'application/octet-stream') -> bool:
        """
        Загружает файл в S3
        """
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=filename,
                Body=content,
                ContentType=content_type
            )
            logger.info(f"Uploaded to S3 successfully: {filename}")
            return True
        except ClientError as e:
            logger.error(f"S3 upload error for {filename}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during S3 upload for {filename}: {str(e)}")
            return False

    def delete_file(self, filename: str) -> bool:
        """
        Удаляет файл из S3
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=filename
            )
            logger.info(f"Deleted from S3: {filename}")
            return True
        except ClientError as e:
            logger.error(f"S3 delete error for {filename}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during S3 delete for {filename}: {str(e)}")
            return False

    def generate_file_url(self, filename: str) -> str:
        """
        Генерирует публичный URL файла в S3
        """
        endpoint_url = os.getenv('AWS_S3_ENDPOINT_URL', '').rstrip('/')
        return f"{endpoint_url}/{self.bucket_name}/{filename}"

    def batch_upload(self, files_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Загружает несколько файлов в S3
        Возвращает словарь с результатами загрузки
        """
        results = {
            'successful': [],
            'failed': []
        }

        for file_data in files_data:
            success = self.upload_file(
                filename=file_data['filename'],
                content=file_data['content'],
                content_type=file_data.get('content_type', 'application/octet-stream')
            )

            if success:
                results['successful'].append({
                    'filename': file_data['filename'],
                    'original_filename': file_data['original_filename'],
                    'index': file_data['index'],
                    'url': self.generate_file_url(file_data['filename'])
                })
            else:
                results['failed'].append({
                    'filename': file_data['original_filename'],
                    'index': file_data['index'],
                    'error': 'Failed to upload to S3'
                })

        return results

    def batch_delete(self, filenames: List[str]) -> bool:
        """
        Удаляет несколько файлов из S3
        """
        success = True
        for filename in filenames:
            if not self.delete_file(filename):
                success = False
        return success

    def validate_connection(self) -> bool:
        """
        Проверяет возможность подключения к S3
        """
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            return True
        except ClientError:
            return False
        except Exception:
            return False