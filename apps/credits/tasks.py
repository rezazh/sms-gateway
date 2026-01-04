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
    synced_user_ids = []
    for key in keys:
        try:
            user_id = int(key.decode('utf-8').split('_')[-1])
            was_synced = CreditService.sync_deltas_to_db(user_id)
            if was_synced:
                count += 1
                synced_user_ids.append(user_id)
        except Exception as e:
            logger.error(f"Error syncing balance for key {key}: {e}")

        if count > 0:
            logger.info(
                f"Synced credit deltas for {count} accounts. User IDs: {synced_user_ids[:5]}...")
        return f"Synced deltas for {count} accounts"