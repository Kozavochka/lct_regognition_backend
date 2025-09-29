import os
import uuid
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from django.conf import settings
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)


class FileService:
    def __init__(self, base_dir: str = None):
        """
        Инициализирует сервис файлов
        :param base_dir: Базовая директория для загрузки файлов (по умолчанию MEDIA_ROOT/uploads/images)
        """
        if base_dir is None:
            self.base_dir = Path(settings.MEDIA_ROOT) / 'uploads' / 'images'
        else:
            self.base_dir = Path(base_dir)

        # Создаем директорию, если её нет
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_file(self, content: bytes, original_filename: str, content_type: str = None) -> Dict[str, Any]:
        """
        Сохраняет файл на сервере
        :param content: Содержимое файла
        :param original_filename: Оригинальное имя файла
        :param content_type: MIME-тип файла
        :return: Словарь с информацией о сохраненном файле
        """
        try:
            # Генерируем уникальное имя файла
            file_extension = Path(original_filename).suffix
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            full_file_path = self.base_dir / unique_filename

            # Сохраняем файл
            with open(full_file_path, 'wb') as f:
                f.write(content)

            # Генерируем URL для доступа к файлу
            file_relative_path = f"uploads/images/{unique_filename}"
            file_url = f"{settings.MEDIA_URL}{file_relative_path}"

            logger.info(f"File saved successfully: {unique_filename}")

            return {
                'filename': unique_filename,
                'original_filename': original_filename,
                'full_path': str(full_file_path),
                'relative_path': file_relative_path,
                'url': file_url,
                'content_type': content_type
            }
        except Exception as e:
            logger.error(f"Error saving file {original_filename}: {str(e)}")
            raise

    def save_files_batch(self, files_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Сохраняет несколько файлов
        :param files_data: Список словарей с данными файлов
        :return: Словарь с результатами (успешные и неуспешные)
        """
        results = {
            'successful': [],
            'failed': []
        }

        for file_data in files_data:
            try:
                file_info = self.save_file(
                    content=file_data['content'],
                    original_filename=file_data['original_filename'],
                    content_type=file_data.get('content_type')
                )
                file_info['index'] = file_data['index']
                results['successful'].append(file_info)
            except Exception as e:
                results['failed'].append({
                    'index': file_data['index'],
                    'original_filename': file_data['original_filename'],
                    'error': str(e)
                })

        return results

    def delete_file(self, relative_path: str) -> bool:
        """
        Удаляет файл с сервера
        :param relative_path: Относительный путь к файлу
        :return: True, если файл успешно удален
        """
        try:
            file_path = Path(settings.MEDIA_ROOT) / relative_path
            if file_path.exists():
                file_path.unlink()
                logger.info(f"File deleted successfully: {relative_path}")
                return True
            else:
                logger.warning(f"File does not exist: {relative_path}")
                return False
        except Exception as e:
            logger.error(f"Error deleting file {relative_path}: {str(e)}")
            return False

    def delete_files_batch(self, relative_paths: List[str]) -> bool:
        """
        Удаляет несколько файлов
        :param relative_paths: Список относительных путей к файлам
        :return: True, если все файлы успешно удалены
        """
        success = True
        for relative_path in relative_paths:
            if not self.delete_file(relative_path):
                success = False
        return success

    def get_file_path(self, filename: str) -> Path:
        """
        Возвращает полный путь к файлу
        :param filename: Имя файла
        :return: Полный путь к файлу
        """
        return self.base_dir / filename

    def file_exists(self, filename: str) -> bool:
        """
        Проверяет существование файла
        :param filename: Имя файла
        :return: True, если файл существует
        """
        return self.get_file_path(filename).exists()

    def get_file_size(self, filename: str) -> Optional[int]:
        """
        Возвращает размер файла в байтах
        :param filename: Имя файла
        :return: Размер файла или None, если файл не существует
        """
        file_path = self.get_file_path(filename)
        if file_path.exists():
            return file_path.stat().st_size
        return None

    def validate_file_type(self, filename: str, allowed_extensions: List[str]) -> bool:
        """
        Проверяет тип файла по расширению
        :param filename: Имя файла
        :param allowed_extensions: Список разрешенных расширений (например, ['.jpg', '.png'])
        :return: True, если тип файла разрешен
        """
        file_extension = Path(filename).suffix.lower()
        return file_extension in [ext.lower() for ext in allowed_extensions]