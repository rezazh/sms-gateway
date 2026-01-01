from decimal import Decimal
from django.db import transaction
from django.core.cache import cache
from django_redis import get_redis_connection
from .models import CreditAccount, CreditTransaction
import logging

logger = logging.getLogger(__name__)


class CreditService:
    CACHE_KEY_PREFIX = 'user_balance_'

    DEDUCT_SCRIPT = """
    local balance = tonumber(redis.call('get', KEYS[1]))
    if not balance then
        return -2 
    end
    local amount = tonumber(ARGV[1])
    if balance < amount then
        return -1
    end
    return redis.call('decrby', KEYS[1], amount)
    """

    @staticmethod
    def get_cache_key(user_id):
        return f"{CreditService.CACHE_KEY_PREFIX}{user_id}"

    @staticmethod
    def get_balance(user):
        cache_key = CreditService.get_cache_key(user.id)
        redis_conn = get_redis_connection("default")
        balance = redis_conn.get(cache_key)

        if balance is None:
            account, _ = CreditAccount.objects.get_or_create(user=user)
            balance = float(account.balance)
            redis_conn.set(cache_key, balance)

        return Decimal(str(balance))

    @staticmethod
    def deduct_balance(user, amount):
        redis_conn = get_redis_connection("default")
        cache_key = CreditService.get_cache_key(user.id)

        if not redis_conn.exists(cache_key):
            CreditService.get_balance(user)

        deduct = redis_conn.register_script(CreditService.DEDUCT_SCRIPT)
        result = deduct(keys=[cache_key], args=[float(amount)])

        if result == -1:
            raise ValueError("Insufficient balance")
        elif result == -2:
            CreditService.get_balance(user)
            return CreditService.deduct_balance(user, amount)

        return True

    @staticmethod
    @transaction.atomic
    def charge_account(user, amount, description=""):
        if amount <= 0:
            raise ValueError("Amount must be positive")

        account, _ = CreditAccount.objects.get_or_create(user=user)

        CreditTransaction.objects.create(
            account=account,
            transaction_type='charge',
            amount=amount,
            balance_before=account.balance,
            balance_after=account.balance + Decimal(str(amount)),
            description=description
        )

        cache_key = CreditService.get_cache_key(user.id)
        redis_conn = get_redis_connection("default")

        if not redis_conn.exists(cache_key):
            redis_conn.set(cache_key, float(account.balance))

        redis_conn.incrbyfloat(cache_key, float(amount))

        logger.info(f"Account charged - User: {user.username}, Amount: {amount}")

    @staticmethod
    def sync_balance_to_db(user_id):
        cache_key = CreditService.get_cache_key(user_id)
        redis_conn = get_redis_connection("default")
        cached_balance = redis_conn.get(cache_key)

        if cached_balance is not None:
            try:
                CreditAccount.objects.filter(user_id=user_id).update(
                    balance=Decimal(cached_balance.decode('utf-8'))
                )
            except Exception as e:
                logger.error(f"Error syncing balance for user {user_id}: {e}")