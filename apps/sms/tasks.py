from decimal import Decimal

from celery import shared_task
from django.utils import timezone

from core.utils import CircuitBreaker
from .models import SMSMessage
import time
import random
from celery.signals import worker_shutting_down

import logging

from .services import SMSStatusBuffer

logger = logging.getLogger(__name__)
IS_SHUTTING_DOWN = False


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


@shared_task(bind=True)
def ingest_sms_task(self, sms_data):
    from django.contrib.auth import get_user_model
    from .models import SMSMessage

    User = get_user_model()

    try:
        sms = SMSMessage.objects.create(
            id=sms_data['id'],
            user_id=sms_data['user_id'],
            recipient=sms_data['recipient'],
            message=sms_data['message'],
            priority=sms_data['priority'],
            cost=Decimal(sms_data['cost']),
            scheduled_at=sms_data['scheduled_at'],
            status='queued'
        )

        if not sms.scheduled_at:
            process_sms_sending.delay(sms.id)

    except Exception as e:
        logger.error(f"Failed to ingest SMS {sms_data['id']}: {e}")


@shared_task(bind=True, max_retries=3)
def process_sms_sending(self, sms_id):

    cb = CircuitBreaker(service_name="sms_provider_primary")

    if cb.is_open():
        logger.warning(f"Circuit Breaker is OPEN. Skipping/Retrying SMS {sms_id}")
        raise self.retry(countdown=60)

    from .models import SMSMessage
    try:
        sms = SMSMessage.objects.get(id=sms_id)
    except SMSMessage.DoesNotExist:
        logger.error(f"SMS {sms_id} not found in DB during sending process.")
        return

    try:
        is_success = random.random() < 0.95

        if is_success:
            cb.record_success()
            SMSStatusBuffer.push_update(str(sms.id), 'sent')
            logger.info(f"SMS {sms_id} sent successfully to {sms.recipient}")

        else:
            error_msg = "Provider rejected: Invalid number"
            SMSStatusBuffer.push_update(str(sms.id), 'failed', error_msg)
            logger.warning(f"SMS {sms_id} failed: {error_msg}")

    except Exception as e:
        logger.error(f"Network/System error sending SMS {sms_id}: {e}")

        cb.record_failure()

        try:

            countdown = 60 * (2 ** self.request.retries)
            raise self.retry(exc=e, countdown=countdown)

        except self.MaxRetriesExceededError:
            SMSStatusBuffer.push_update(str(sms.id), 'failed', f"Max retries exceeded: {e}")
            logger.critical(f"SMS {sms_id} permanently failed after retries.")


@worker_shutting_down.connect
def worker_shutting_down_handler(sig, how, exitcode, **kwargs):
    global IS_SHUTTING_DOWN
    IS_SHUTTING_DOWN = True
    print("Worker is shutting down, stopping new heavy tasks...")


@shared_task
def flush_sms_buffer_task():
    from .services import SMSStatusBuffer
    if IS_SHUTTING_DOWN:
        return "Skipped flush due to shutdown"
    SMSStatusBuffer.flush_buffer()
    return "Buffer flushed"