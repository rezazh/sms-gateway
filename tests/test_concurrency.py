import pytest
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from django.db import connection
from apps.credits.services import CreditService

pytestmark = pytest.mark.django_db(transaction=True)


def test_concurrent_balance_deduction(user_with_credit, mock_redis):
    user = user_with_credit
    cache_key = CreditService.get_cache_key(user.id)

    user.credit_account.balance = Decimal('100.00')
    user.credit_account.save()
    mock_redis.set(cache_key, '100.00')

    def attempt_deduct():
        try:
            connection.close()
            result = CreditService.deduct_balance(user, 20)
            return "success"
        except ValueError:
            return "insufficient"
        except Exception as e:
            return f"error: {str(e)}"

    workers = 10
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(lambda _: attempt_deduct(), range(workers)))

    success_count = results.count("success")
    insufficient_count = results.count("insufficient")

    print(f"\nConcurrency Results: Success={success_count}, Insufficient={insufficient_count}, Other={results}")

    assert success_count == 5, f"Expected 5 successful deductions, got {success_count}"
    assert insufficient_count == 5, f"Expected 5 insufficient failures, got {insufficient_count}"

    final_balance_redis = Decimal(mock_redis.get(cache_key))
    assert final_balance_redis == Decimal('0.00'), f"Redis Balance mismatch: {final_balance_redis}"



def test_concurrent_api_charging(api_client, user):
    api_client.credentials(HTTP_X_API_KEY=user.api_key)
    url = '/api/credits/charge/'
    data = {'amount': '100.00'}

    def charge_call():
        connection.close()
        try:
            CreditService.charge_account(user, 100)
            return True
        except Exception:
            return False

    workers = 5
    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(lambda _: charge_call(), range(workers)))

    user.credit_account.refresh_from_db()

    expected_balance = Decimal('500.00')
    assert user.credit_account.balance == expected_balance