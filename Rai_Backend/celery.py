import os
from celery import Celery
from celery.signals import task_failure
import logging
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Rai_Backend.settings')

app = Celery('Rai_Backend')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

logger = logging.getLogger(__name__)

@task_failure.connect
def log_task_failure(sender=None, task_id=None, exception=None, **kwargs):
    logger.error(f"Task {sender.name} (ID: {task_id}) failed: {exception}", exc_info=True)

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    logger.info(f'Request: {self.request!r}')

app.conf.beat_schedule = {
    'sync-odds-every-5-minutes': {
        'task': 'betting.tasks.sync_odds_data',
        'schedule': crontab(minute='*/5'),
    },
}    