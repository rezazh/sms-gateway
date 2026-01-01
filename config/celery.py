import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('sms_gateway')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'sync-balances-every-minute': {
        'task': 'apps.credits.tasks.sync_all_balances',
        'schedule': 60.0,
    },
    'process-scheduled-sms': {
        'task': 'apps.sms.tasks.process_scheduled_sms',
        'schedule': 30.0,
    },
    'flush-sms-statuses': {
        'task': 'apps.sms.tasks.flush_sms_buffer_task',
        'schedule': 5.0,
    },
}