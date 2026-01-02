from celery import shared_task
from django.contrib.auth import get_user_model
from django.core.cache import cache
from .services import CreditService
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task
def sync_all_balances():
    from django_redis import get_redis_connection
    redis_conn = get_redis_connection("default")

    pattern = f"{CreditService.PENDING_DEDUCT_PREFIX}*"
    keys = redis_conn.keys(pattern)

    count = 0
    for key in keys:
        try:
            user_id = int(key.decode('utf-8').split('_')[-1])
            CreditService.sync_deltas_to_db(user_id)
            count += 1
        except Exception as e:
            logger.error(f"Error syncing balance for key {key}: {e}")

    return f"Synced deltas for {count} accounts"