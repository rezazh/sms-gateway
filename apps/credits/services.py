from decimal import Decimal, ROUND_DOWN
from django.db import transaction
from django_redis import get_redis_connection
from django.conf import settings
from .models import CreditAccount, CreditTransaction
import logging
from django.db.models import F
import time

logger = logging.getLogger(__name__)


class CreditService:
    CACHE_KEY_PREFIX = 'user_balance_'
    PENDING_DEDUCT_PREFIX = 'pending_deduct_'
    LOCK_PREFIX = 'lock_balance_'
    LOCK_TIMEOUT = 5  # seconds

    DEDUCT_SCRIPT = """
        local balance_str = redis.call('get', KEYS[1])
        if not balance_str then
            return -2 -- Cache Miss
        end

        local amount_str = ARGV[1]
        local balance = tonumber(balance_str)
        local amount = tonumber(amount_str)

        if not balance or not amount then
            return -3 -- Invalid Data in cache or arguments
        end

        if balance < amount then
            return -1 -- Insufficient Funds
        end

        redis.call('incrbyfloat', KEYS[1], -amount)
        redis.call('incrbyfloat', KEYS[2], amount)
        return 1
        """

    @staticmethod
    def get_transactions(user, limit=100):
        account = CreditService.get_or_create_account(user)
        return CreditTransaction.objects.filter(account=account).order_by('-created_at')[:limit]

    @staticmethod
    def get_or_create_account(user):
        account, _ = CreditAccount.objects.get_or_create(user=user)
        return account

    @staticmethod
    def get_cache_key(user_id):
        return f"{CreditService.CACHE_KEY_PREFIX}{user_id}"

    @staticmethod
    def get_pending_key(user_id):
        return f"{CreditService.PENDING_DEDUCT_PREFIX}{user_id}"

    @staticmethod
    def get_lock_key(user_id):
        return f"{CreditService.LOCK_PREFIX}{user_id}"

    @staticmethod
    def get_balance(user):
        cache_key = CreditService.get_cache_key(user.id)
        redis_conn = get_redis_connection("default")

        balance = redis_conn.get(cache_key)
        if balance is not None:
            return Decimal(balance.decode('utf-8') if isinstance(balance, bytes) else str(balance))

        lock_key = CreditService.get_lock_key(user.id)

        with redis_conn.lock(lock_key, timeout=CreditService.LOCK_TIMEOUT, blocking_timeout=3):
            balance = redis_conn.get(cache_key)
            if balance is not None:
                return Decimal(balance.decode('utf-8') if isinstance(balance, bytes) else str(balance))

            logger.info(f"Cache miss for user {user.id}, fetching from DB inside lock.")
            account, _ = CreditAccount.objects.get_or_create(user=user)
            current_balance_str = str(account.balance)

            redis_conn.set(cache_key, current_balance_str)

            return account.balance

    @staticmethod
    def deduct_balance(user, amount):
        redis_conn = get_redis_connection("default")
        cache_key = CreditService.get_cache_key(user.id)
        pending_key = CreditService.get_pending_key(user.id)

        amount_str = str(amount)

        if not redis_conn.exists(cache_key):
            CreditService.get_balance(user)

        deduct = redis_conn.register_script(CreditService.DEDUCT_SCRIPT)

        result = deduct(keys=[cache_key, pending_key], args=[amount_str])

        if result == 1:
            return True

        elif result == -1:
            raise ValueError("Insufficient balance")

        elif result == -2:
            logger.warning(f"Balance key evaporated for user {user.id}, retrying deduction.")
            CreditService.get_balance(user)
            retry_result = deduct(keys=[cache_key, pending_key], args=[amount_str])

            if retry_result == 1:
                return True
            elif retry_result == -1:
                raise ValueError("Insufficient balance")
            else:
                raise ValueError(f"System error during deduction code: {retry_result}")


        elif result == -3:
            logger.critical(f"Invalid data found in cache for user {user.id}. Cache key: {cache_key}")
            redis_conn.delete(cache_key)

            raise ValueError("System error: Corrupted balance data")

        return False

    @classmethod
    def sync_deltas_to_db(cls, user_id):
        redis_conn = get_redis_connection("default")
        pending_key = cls.get_pending_key(user_id)

        try:
            delta = redis_conn.get(pending_key)

            if delta:
                delta_val = Decimal(str(float(delta)))  # Convert safe
                if delta_val > 0:
                    with transaction.atomic():
                        account = CreditAccount.objects.select_for_update().get(user_id=user_id)

                        account.balance -= delta_val
                        account.total_spent += delta_val
                        account.save()

                        redis_conn.incrbyfloat(pending_key, -float(delta_val))
                    return True

        except Exception as e:
            logger.error(f"Error syncing delta for user {user_id}: {str(e)}")
        return False

    @staticmethod
    @transaction.atomic
    def charge_account(user, amount, description=""):
        if amount <= 0:
            raise ValueError("Amount must be positive")

        account, _ = CreditAccount.objects.select_for_update().get_or_create(user=user)

        amount_decimal = Decimal(str(amount))
        account.balance += amount_decimal
        account.total_charged += amount_decimal
        account.save()

        CreditTransaction.objects.create(
            account=account,
            transaction_type='charge',
            amount=amount_decimal,
            balance_before=account.balance - amount_decimal,
            balance_after=account.balance,
            description=description
        )

        cache_key = CreditService.get_cache_key(user.id)
        redis_conn = get_redis_connection("default")

        if redis_conn.exists(cache_key):
            redis_conn.incrbyfloat(cache_key, float(amount))
        else:
            redis_conn.set(cache_key, str(account.balance))

        logger.info(f"Account charged - User: {user.username}, Amount: {amount}")
        return account

    @staticmethod
    def sync_balance_to_db(user_id):
        cache_key = CreditService.get_cache_key(user_id)
        redis_conn = get_redis_connection("default")
        cached_balance = redis_conn.get(cache_key)

        if cached_balance is not None:
            pass