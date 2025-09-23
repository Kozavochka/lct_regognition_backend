# import os
# import uuid
# import boto3
# from rest_framework.views import APIView
# from rest_framework.response import Response
# from rest_framework import status
# from .models import UploadedImage
# from .serializers import UploadedImageSerializer
#
#
# class UploadImageView(APIView):
#     def post(self, request, *args, **kwargs):
#         files = request.FILES.getlist("image")
#
#         if not files:
#             return Response({"error": "No files uploaded"}, status=status.HTTP_400_BAD_REQUEST)
#
#         # Создаем S3 клиент
#         s3_client = boto3.client(
#             's3',
#             aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
#             aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
#             region_name=os.getenv('AWS_S3_REGION_NAME', 'eu-central-1')
#         )
#
#         bucket_name = os.getenv('AWS_STORAGE_BUCKET_NAME')
#
#         # Сначала валидируем все файлы
#         validated_files = []
#         validation_errors = []
#
#         for i, file_obj in enumerate(files):
#             try:
#                 # Проверяем, что файл существует
#                 if not file_obj:
#                     validation_errors.append({
#                         "file_index": i,
#                         "filename": f"file_{i}",
#                         "error": "Empty or missing file"
#                     })
#                     continue
#
#                 # Генерируем уникальное имя
#                 filename = f"{uuid.uuid4()}_{file_obj.name}"
#
#                 # Читаем содержимое файла
#                 file_content = file_obj.read()
#
#                 validated_files.append({
#                     'filename': filename,
#                     'content': file_content,
#                     'original_filename': file_obj.name,
#                     'index': i
#                 })
#
#             except Exception as e:
#                 validation_errors.append({
#                     "file_index": i,
#                     "filename": file_obj.name if file_obj else f"file_{i}",
#                     "error": str(e)
#                 })
#
#         # Если были ошибки валидации - возвращаем их
#         if validation_errors:
#             return Response({
#                 "validation_errors": validation_errors
#             }, status=status.HTTP_400_BAD_REQUEST)
#
#         # Если все файлы прошли валидацию - загружаем их все
#         uploaded_images = []
#         upload_errors = []
#
#         try:
#             for validated_file in validated_files:
#                 try:
#                     # Загружаем файл в S3 напрямую
#                     s3_client.put_object(
#                         Bucket=bucket_name,
#                         Key=validated_file['filename'],
#                         Body=validated_file['content'],
#                         ContentType=getattr(files[validated_file['index']], 'content_type', 'application/octet-stream')
#                     )
#
#                     # Генерируем URL файла
#                     region = os.getenv('AWS_S3_REGION_NAME', 'eu-central-1')
#                     file_url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{validated_file['filename']}"
#
#                     # Сохраняем в БД
#                     uploaded = UploadedImage.objects.create(
#                         filename=validated_file['filename'],
#                         s3_url=file_url
#                     )
#                     uploaded_images.append(uploaded)
#
#                 except Exception as e:
#                     upload_errors.append({
#                         "file_index": validated_file['index'],
#                         "filename": validated_file['original_filename'],
#                         "error": str(e)
#                     })
#
#                     # Откатываем уже загруженные файлы
#                     for uploaded_image in uploaded_images:
#                         try:
#                             uploaded_image.delete()
#                             # Удаляем файл из S3
#                             s3_client.delete_object(
#                                 Bucket=bucket_name,
#                                 Key=uploaded_image.filename
#                             )
#                         except:
#                             pass
#
#                     # Прерываем загрузку остальных файлов
#                     break
#
#             # Если были ошибки при загрузке
#             if upload_errors:
#                 return Response({
#                     "error": "Upload failed",
#                     "details": "Server error occurred during file upload"
#                 }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
#
#             # Если все успешно загрузилось - возвращаем только сериализованные данные
#             serializer = UploadedImageSerializer(uploaded_images, many=True)
#             return Response(serializer.data, status=status.HTTP_201_CREATED)
#
#         except Exception as e:
#             # Откатываем все загруженные файлы в случае критической ошибки
#             for uploaded_image in uploaded_images:
#                 try:
#                     uploaded_image.delete()
#                     # Удаляем файл из S3
#                     s3_client.delete_object(
#                         Bucket=bucket_name,
#                         Key=uploaded_image.filename
#                     )
#                 except:
#                     pass
#
#             return Response({
#                 "error": "Upload failed",
#                 "details": "Server error occurred during file upload"
#             }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


import os
import uuid
import boto3
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.files.base import ContentFile
from botocore.exceptions import ClientError
from .models import UploadedImage
from .serializers import UploadedImageSerializer

logger = logging.getLogger(__name__)


class UploadImageView(APIView):
    def post(self, request, *args, **kwargs):
        files = request.FILES.getlist("image")

        if not files:
            return Response({"error": "No files uploaded"}, status=status.HTTP_400_BAD_REQUEST)

        # Создаем S3 клиент напрямую
        s3_client = boto3.client(
            's3',
            endpoint_url=os.getenv('AWS_S3_ENDPOINT_URL'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_S3_REGION_NAME', 'us-east-1'),
        )

        bucket_name = os.getenv('AWS_STORAGE_BUCKET_NAME')

        # Сначала валидируем все файлы
        validated_files = []
        validation_errors = []

        for i, file_obj in enumerate(files):
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
                    'filename': filename,
                    'content': file_content,
                    'original_filename': file_obj.name,
                    'index': i
                })

            except Exception as e:
                validation_errors.append({
                    "file_index": i,
                    "filename": file_obj.name if file_obj else f"file_{i}",
                    "error": str(e)
                })

        if validation_errors:
            return Response({
                "validation_errors": validation_errors
            }, status=status.HTTP_400_BAD_REQUEST)

        uploaded_images = []
        upload_errors = []

        try:
            for validated_file in validated_files:
                try:
                    logger.info(f"Uploading to S3: {validated_file['filename']}")

                    # Загружаем файл в S3 напрямую
                    s3_client.put_object(
                        Bucket=bucket_name,
                        Key=validated_file['filename'],
                        Body=validated_file['content'],
                        ContentType=getattr(files[validated_file['index']], 'content_type', 'application/octet-stream')
                    )
                    logger.info(f"Uploaded to S3 successfully: {validated_file['filename']}")

                    # Генерируем URL файла
                    endpoint_url = os.getenv('AWS_S3_ENDPOINT_URL').rstrip('/')
                    file_url = f"{endpoint_url}/{bucket_name}/{validated_file['filename']}"

                    # Сохраняем в БД
                    uploaded = UploadedImage.objects.create(
                        filename=validated_file['filename'],
                        s3_url=file_url
                    )
                    uploaded_images.append(uploaded)
                    logger.info(f"Database record created: {validated_file['filename']}")

                except Exception as e:
                    logger.error(f"Upload error for {validated_file['filename']}: {str(e)}")
                    upload_errors.append({
                        "file_index": validated_file['index'],
                        "filename": validated_file['original_filename'],
                        "error": str(e)
                    })

                    # Откатываем уже загруженные файлы
                    for uploaded_image in uploaded_images:
                        try:
                            uploaded_image.delete()
                            s3_client.delete_object(
                                Bucket=bucket_name,
                                Key=uploaded_image.filename
                            )
                        except Exception as delete_error:
                            logger.error(f"Error deleting {uploaded_image.filename}: {str(delete_error)}")

                    break

            if upload_errors:
                return Response({
                    "error": "Upload failed",
                    "details": "Server error occurred during file upload"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            serializer = UploadedImageSerializer(uploaded_images, many=True)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Critical error: {str(e)}")
            for uploaded_image in uploaded_images:
                try:
                    uploaded_image.delete()
                    s3_client.delete_object(
                        Bucket=bucket_name,
                        Key=uploaded_image.filename
                    )
                except Exception as delete_error:
                    logger.error(f"Error deleting {uploaded_image.filename}: {str(delete_error)}")

            return Response({
                "error": "Upload failed",
                "details": "Server error occurred during file upload"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)