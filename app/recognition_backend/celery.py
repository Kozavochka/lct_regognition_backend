import os
from celery import Celery

from recognition_backend.settings import REDIS_PASSWORD, REDIS_HOST, REDIS_PORT

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'recognition_backend.settings')

app = Celery('recognition_backend')

app.config_from_object('django.conf:settings', namespace='CELERY')

# Брокер и бэкенд через Redis
broker_url = (
    f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/0"
)

app.conf.broker_url = broker_url
app.conf.result_backend = broker_url

app.autodiscover_tasks()