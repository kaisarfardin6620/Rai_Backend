import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Rai_Backend.settings')

app = Celery('Rai_Backend')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()