from decimal import Decimal

from celery import shared_task
from django.utils import timezone
from prometheus_client import Counter
from django.db import connection
from django.core.cache import cache

from core.utils import CircuitBreaker
from .models import SMSMessage
import time
import random
from celery.signals import worker_shutting_down

import logging

from .services import SMSStatusBuffer

logger = logging.getLogger(__name__)
IS_SHUTTING_DOWN = False
SMS_SENT_TOTAL = Counter('sms_sent_total', 'Total SMS sent successfully', ['priority'])
SMS_FAILED_TOTAL = Counter('sms_failed_total', 'Total SMS failed', ['priority', 'reason'])

@shared_task(bind=True, max_retries=3)
def send_sms_task(self, sms_id):
    from .models import SMSMessage

    try:
        sms = SMSMessage.objects.only('recipient', 'message', 'retry_count').get(id=sms_id)

        logger.info(f"Starting SMS send - ID: {sms_id}")

        time.sleep(0.5)

        if random.random() < 0.9:
            SMSStatusBuffer.push_update(str(sms.id), 'sent')
            SMS_SENT_TOTAL.labels(priority=sms.priority).inc()

            logger.debug(f"SMS sent successfully - ID: {sms_id}")
            return {'status': 'success'}
        else:
            raise Exception("SMS provider error")

    except SMSMessage.DoesNotExist:
        logger.error(f"SMS not found - ID: {sms_id}")
        return

    except Exception as e:
        error_msg = str(e)
        SMSStatusBuffer.push_update(str(sms.id), 'failed', error_msg)
        SMS_FAILED_TOTAL.labels(priority=sms.priority, reason="provider_error").inc()

        logger.error(f"SMS send failed - ID: {sms_id}: {error_msg}")

        if sms.retry_count < 3:
            raise self.retry(exc=e, countdown=60)

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


@shared_task
def batch_ingest_sms():
    LOCK_ID = "lock_batch_ingest_sms"
    LOCK_EXPIRE = 60 * 5

    acquire_lock = cache.add(LOCK_ID, "true", timeout=LOCK_EXPIRE)

    if not acquire_lock:
        logger.warning("Previous batch ingestion is still running. Skipping this run.")
        return "Skipped (Locked)"

    try:
        from .services import SMSService
        processed_count = SMSService.process_ingest_buffer(batch_size=5000)

        if processed_count > 0:
            logger.info(f"Ingested {processed_count} new SMS messages into database.")
        return f"Ingested {processed_count} messages"

    except Exception as e:
        logger.error(f"Error during batch ingest: {e}")
        raise e

    finally:
        cache.delete(LOCK_ID)


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
            logger.debug(f"SMS {sms_id} sent successfully to {sms.recipient}")
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
    updated_count = SMSStatusBuffer.flush_buffer()
    logger.debug(f"Flush buffer task ran. Updated {updated_count} statuses.")
    return f"Buffer flushed, {updated_count} items processed"


@shared_task
def maintain_partitions():
    now = timezone.now()
    next_year = now.year + 1
    table_name = 'sms_messages'
    partition_name = f"{table_name}_y{next_year}"

    start_date = f"{next_year}-01-01 00:00:00+00"
    end_date = f"{next_year + 1}-01-01 00:00:00+00"

    check_sql = """
                SELECT 1
                FROM pg_class c
                         JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = %s; \
                """

    create_sql = f"""
        CREATE TABLE IF NOT EXISTS {partition_name} PARTITION OF {table_name}
        FOR VALUES FROM ('{start_date}') TO ('{end_date}');
    """

    create_idx_sql = f"""
        CREATE INDEX IF NOT EXISTS {partition_name}_created_at_idx 
        ON {partition_name} (created_at);
    """

    try:
        with connection.cursor() as cursor:
            cursor.execute(check_sql, [partition_name])
            exists = cursor.fetchone()

            if not exists:
                logger.info(f"Creating partition for year {next_year}: {partition_name}")
                cursor.execute(create_sql)
                cursor.execute(create_idx_sql)
                return f"Created partition {partition_name}"
            else:
                return f"Partition {partition_name} already exists"

    except Exception as e:
        logger.error(f"Failed to maintain partitions: {e}")
        raise e