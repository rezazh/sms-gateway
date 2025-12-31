from celery import shared_task
from django.utils import timezone
from .models import SMSMessage
import time
import random

import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def send_sms_task(self, sms_id):
    try:
        sms = SMSMessage.objects.get(id=sms_id)

        logger.info(f"Starting SMS send - ID: {sms_id}")

        sms.status = 'sending'
        sms.save()

        time.sleep(2)

        if random.random() < 0.9:
            sms.mark_as_sent()
            logger.info(
                f"SMS sent successfully - ID: {sms_id}, "
                f"Recipient: {sms.recipient}"
            )
            return {
                'status': 'success',
                'sms_id': str(sms.id),
                'recipient': sms.recipient
            }
        else:
            raise Exception("SMS provider error")

    except SMSMessage.DoesNotExist:
        logger.error(f"SMS not found - ID: {sms_id}")
        return {'status': 'error', 'message': 'SMS not found'}

    except Exception as e:
        sms.mark_as_failed(str(e))
        logger.error(
            f"SMS send failed - ID: {sms_id}, "
            f"Error: {str(e)}, Retry count: {sms.retry_count}"
        )

        if sms.can_retry():
            logger.info(f"Retrying SMS - ID: {sms_id}")
            raise self.retry(exc=e, countdown=60)

        return {
            'status': 'failed',
            'sms_id': str(sms.id),
            'reason': str(e)
        }

@shared_task
def process_scheduled_sms():
    now = timezone.now()

    scheduled_messages = SMSMessage.objects.filter(
        status='queued',
        scheduled_at__lte=now
    )

    count = 0
    for sms in scheduled_messages:
        send_sms_task.delay(str(sms.id))
        count += 1

    return {
        'status': 'success',
        'processed': count
    }


@shared_task
def retry_failed_sms():
    failed_messages = SMSMessage.objects.filter(
        status='failed'
    )

    count = 0
    for sms in failed_messages:
        if sms.can_retry():
            send_sms_task.delay(str(sms.id))
            count += 1

    return {
        'status': 'success',
        'retried': count
    }