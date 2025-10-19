import requests
import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

def _send_geo_request_internal(images):
    """
        Отправляет POST-запрос на внешний сервис для обработки списка изображений.

        Args:
            images (list): Список словарей с ключами 'image_id' и 'image_path'.

        Returns:
            dict: {
                'success': list of task_ids successfully queued,
                'errors': list of dicts with {'task_id', 'error'},
                'raw_response': original response dict (optional)
            }
    """
    main_callback_url = f"{settings.API_BASE_URL}:8000/api/update-image-result/"
    trash_callback_url = f"{settings.API_BASE_URL}:8000/api/update-image-trash-result/"
    url = f"{settings.EXTERNAL_SERVICE_URL}:8080/api/Prediction"

    tasks = []
    for img in images:
        task_id = img['task_id']
        image_filename = img['image_filename']
        angle = img['angle']
        height = img['height']
        lat = img['lat']
        lon = img['lon']
        tasks.append({
            "fileName": image_filename,
            "taskId": str(task_id),
            "angle": angle,
            "height": height,
            "lat": lat,
            "lon": lon,
        })

    payload = {
        "mainCallback": main_callback_url,
        "callbackUrl":main_callback_url, # Для обратной совместимости
        "trashCallback": trash_callback_url,
        "tasks": tasks
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "*/*"
    }

    try:
        logger.info(f"Sending geo request for {len(tasks)} images")
        logger.debug(f"Payload: {json.dumps(payload, indent=2)}")

        response = requests.post(url, data=json.dumps(payload), headers=headers, timeout=30)

        logger.info(f"Geo service response status: {response.status_code}")

        if response.status_code == 202:
            try:
                result = response.json()
                logger.info(f"Geo service returned: {result}")

                # Извлекаем успешные job и ошибки
                jobs = result.get("jobs", [])
                validation_errors = result.get("validationErrors", [])

                # Формируем структурированный ответ
                structured_result = {
                    'success': [job for job in jobs],  # можно преобразовать в int, если нужно
                    'errors': [
                        {
                            'task_id': error.get('taskId'),
                            'error': error.get('error')
                        }
                        for error in validation_errors
                    ],
                    'raw_response': result  # опционально, для отладки
                }

                return structured_result

            except ValueError:
                logger.error("Geo service returned invalid JSON")
                return {
                    'success': [],
                    'errors': [],
                    'raw_response': None
                }
        else:
            logger.error(f"Geo service returned non-202 status: {response.status_code}, body: {response.text}")
            return {
                'success': [],
                'errors': [],
                'raw_response': None
            }

    except Exception as e:
        logger.error(f"Exception while calling geo service: {e}", exc_info=True)
        return {
            'success': [],
            'errors': [],
            'raw_response': None
        }