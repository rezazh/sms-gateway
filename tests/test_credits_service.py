import pytest
from decimal import Decimal

pytestmark = pytest.mark.django_db


def test_get_balance_cache_miss(user, credit_account, credit_service, mock_redis):
    cache_key = credit_service.get_cache_key(user.id)
    mock_redis.delete(cache_key)

    balance = credit_service.get_balance(user)

    assert balance == Decimal('1000')
    assert mock_redis.get(cache_key) == '1000.00'

def test_get_balance_cache_hit(user, credit_service, mock_redis):
    cache_key = credit_service.get_cache_key(user.id)
    mock_redis.set(cache_key, '500.50')

    balance = credit_service.get_balance(user)

    assert balance == Decimal('500.50')

def test_deduct_balance_success(credit_account, credit_service, mock_redis):
    user = credit_account.user
    credit_service.get_balance(user)

    result = credit_service.deduct_balance(user, 100)

    assert result is True
    assert credit_service.get_balance(user) == Decimal('900')

    credit_account.refresh_from_db()
    assert credit_account.balance == Decimal('1000')

    pending_key = credit_service.get_pending_key(user.id)
    assert float(mock_redis.get(pending_key)) == 100.0

def test_deduct_balance_insufficient(credit_account, credit_service, mock_redis):
    user = credit_account.user
    credit_service.get_balance(user)

    with pytest.raises(ValueError, match="Insufficient balance"):
        credit_service.deduct_balance(user, 5000)

    assert credit_service.get_balance(user) == Decimal('1000')

def test_charge_account(user, credit_service, mock_redis):
    initial_balance = credit_service.get_balance(user)
    assert initial_balance == Decimal('0')

    account = credit_service.charge_account(user, 500, "Test charge")

    assert account.balance == Decimal('500')
    assert account.total_charged == Decimal('500')

    assert credit_service.get_balance(user) == Decimal('500')

    from apps.credits.models import CreditTransaction
    assert CreditTransaction.objects.count() == 1
    tx = CreditTransaction.objects.first()
    assert tx.amount == Decimal('500')
    assert tx.transaction_type == 'charge'

def test_sync_deltas_to_db(credit_account, credit_service, mock_redis):
    user = credit_account.user
    credit_service.get_balance(user)

    credit_service.deduct_balance(user, 100)
    credit_service.deduct_balance(user, 50)

    assert credit_service.get_balance(user) == Decimal('850')
    pending_key = credit_service.get_pending_key(user.id)
    assert float(mock_redis.get(pending_key)) == 150.0

    credit_service.sync_deltas_to_db(user.id)

    credit_account.refresh_from_db()
    assert credit_account.balance == Decimal('850')
    assert credit_account.total_spent == Decimal('150')

    assert float(mock_redis.get(pending_key)) == 0.0