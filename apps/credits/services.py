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
        return -2 -- Balance not cached
    end
    local amount = tonumber(ARGV[1])
    if balance < amount then
        return -1 -- Insufficient balance
    end
    return redis.call('decrby', KEYS[1], amount)
    """

    @staticmethod
    def get_cache_key(user_id):
        return f"{CreditService.CACHE_KEY_PREFIX}{user_id}"

    @staticmethod
    def get_or_create_account(user):
        account, created = CreditAccount.objects.get_or_create(user=user)
        cache_key = CreditService.get_cache_key(user.id)
        if cache.get(cache_key) is None:
            cache.set(cache_key, float(account.balance), timeout=None)
        return account

    @staticmethod
    def get_balance_cache(user):
        cache_key = CreditService.get_cache_key(user.id)
        balance = cache.get(cache_key)

        if balance is None:
            account = CreditService.get_or_create_account(user)
            balance = float(account.balance)
            cache.set(cache_key, balance, timeout=None)

        return Decimal(str(balance))

    @staticmethod
    def deduct_balance_cache(user, amount):
        redis_conn = get_redis_connection("default")
        cache_key = CreditService.get_cache_key(user.id)

        if not redis_conn.exists(cache_key):
            CreditService.get_balance_cache(user)

        deduct = redis_conn.register_script(CreditService.DEDUCT_SCRIPT)
        result = deduct(keys=[cache_key], args=[float(amount)])

        if result == -1:
            logger.warning(f"Insufficient balance in Cache for user {user.username}")
            raise ValueError("Insufficient balance")
        elif result == -2:
            CreditService.get_balance_cache(user)
            return CreditService.deduct_balance_cache(user, amount)  # Retry

        return True

    @staticmethod
    @transaction.atomic
    def charge_account(user, amount, description=""):
        if amount <= 0:
            raise ValueError("Amount must be positive")

        account = CreditService.get_or_create_account(user)
        balance_before = account.balance

        account.charge(amount)

        cache_key = CreditService.get_cache_key(user.id)
        redis_conn = get_redis_connection("default")
        redis_conn.incrbyfloat(cache_key, float(amount))

        CreditTransaction.objects.create(
            account=account,
            transaction_type='charge',
            amount=amount,
            balance_before=balance_before,
            balance_after=account.balance,
            description=description
        )

        logger.info(f"Account charged - User: {user.username}, Amount: {amount}")
        return account

    @staticmethod
    def sync_balance_to_db(user_id):
        cache_key = CreditService.get_cache_key(user_id)
        cached_balance = cache.get(cache_key)

        if cached_balance is not None:
            with transaction.atomic():
                account = CreditAccount.objects.select_for_update().get(user_id=user_id)
                if abs(float(account.balance) - float(cached_balance)) > 0.001:
                    diff = Decimal(str(cached_balance)) - account.balance
                    account.balance = Decimal(str(cached_balance))
                    account.total_spent += abs(diff) if diff < 0 else 0
                    account.save()
                    logger.info(f"Synced balance for user {user_id}: {account.balance}")

    @staticmethod
    def get_transactions(user, limit=100):
        account = CreditService.get_or_create_account(user)
        return account.transactions.all()[:limit]