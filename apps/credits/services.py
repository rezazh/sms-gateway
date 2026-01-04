from decimal import Decimal
from django.db import transaction
from django.core.cache import cache
from django_redis import get_redis_connection
from .models import CreditAccount, CreditTransaction
import logging
from django.db.models import F

logger = logging.getLogger(__name__)


class CreditService:
    CACHE_KEY_PREFIX = 'user_balance_'
    PENDING_DEDUCT_PREFIX = 'pending_deduct_'

    DEDUCT_SCRIPT = """
    local balance = tonumber(redis.call('get', KEYS[1]))
    if not balance then
        return -2 
    end
    local amount = tonumber(ARGV[1])
    if balance < amount then
        return -1
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
    def get_balance(user):
        cache_key = CreditService.get_cache_key(user.id)
        redis_conn = get_redis_connection("default")
        balance = redis_conn.get(cache_key)

        if balance is None:
            account, _ = CreditAccount.objects.get_or_create(user=user)
            redis_conn.set(cache_key, str(account.balance))
            return account.balance

        if isinstance(balance, bytes):
            balance = balance.decode('utf-8')

        return Decimal(str(balance))

    @staticmethod
    def deduct_balance(user, amount):
        redis_conn = get_redis_connection("default")
        cache_key = CreditService.get_cache_key(user.id)
        pending_key = CreditService.get_pending_key(user.id)

        if not redis_conn.exists(cache_key):
            CreditService.get_balance(user)

        deduct = redis_conn.register_script(CreditService.DEDUCT_SCRIPT)
        result = deduct(keys=[cache_key, pending_key], args=[float(amount)])

        if result == -1:
            raise ValueError("Insufficient balance")

        elif result == -2:
            CreditService.get_balance(user)
            result = deduct(keys=[cache_key, pending_key], args=[float(amount)])
            if result == -1:
                raise ValueError("Insufficient balance")

        return True

    @classmethod
    def sync_deltas_to_db(cls, user_id):
        redis_conn = get_redis_connection("default")
        pending_key = cls.get_pending_key(user_id)

        try:
            delta = redis_conn.get(pending_key)

            if delta:
                delta = float(delta)
                if delta != 0:
                    with transaction.atomic():
                        account = CreditAccount.objects.select_for_update().get(user_id=user_id)
                        amount_decimal = Decimal(str(delta))

                        account.balance -= amount_decimal
                        account.total_spent += amount_decimal

                        account.save()

                        redis_conn.incrbyfloat(pending_key, -delta)
                    return True

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error syncing delta for user {user_id}: {str(e)}")
        return False

    @staticmethod
    @transaction.atomic
    def charge_account(user, amount, description=""):
        if amount <= 0:
            raise ValueError("Amount must be positive")

        account, _ = CreditAccount.objects.get_or_create(user=user)

        account.balance = F('balance') + Decimal(str(amount))
        account.total_charged = F('total_charged') + Decimal(str(amount))
        account.save()
        account.refresh_from_db()

        CreditTransaction.objects.create(
            account=account,
            transaction_type='charge',
            amount=amount,
            balance_before=account.balance - Decimal(str(amount)),
            balance_after=account.balance,
            description=description
        )

        cache_key = CreditService.get_cache_key(user.id)
        redis_conn = get_redis_connection("default")
        redis_conn.incrbyfloat(cache_key, float(amount))

        logger.info(f"Account charged - User: {user.username}, Amount: {amount}")
        return account

    @staticmethod
    def sync_balance_to_db(user_id):
        cache_key = CreditService.get_cache_key(user_id)
        redis_conn = get_redis_connection("default")
        cached_balance = redis_conn.get(cache_key)

        if cached_balance is not None:
            if isinstance(cached_balance, bytes):
                cached_balance = cached_balance.decode('utf-8')
            try:
                CreditAccount.objects.filter(user_id=user_id).update(
                    balance=Decimal(cached_balance)
                )
            except Exception as e:
                logger.error(f"Error syncing balance for user {user_id}: {e}")