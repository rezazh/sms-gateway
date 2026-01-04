import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal
import uuid
from django.conf import settings
from apps.sms.services import SMSService
from core.utils import CircuitBreaker

pytestmark = pytest.mark.django_db


def test_api_idempotency_duplicate_request(api_client, user_with_credit, mock_redis):
    api_client.credentials(HTTP_X_API_KEY=user_with_credit.api_key)
    request_id = str(uuid.uuid4())
    headers = {'HTTP_X_REQUEST_ID': request_id}

    url = '/api/sms/send/'
    data = {'recipient': '09121112233', 'message': 'Idempotency Test'}

    response1 = api_client.post(url, data, format='json', **headers)
    assert response1.status_code == 202

    response2 = api_client.post(url, data, format='json', **headers)
    assert response2.status_code == 409
    assert response2.data['error'] == "Duplicate request"


def test_sms_task_retry_mechanism(user_with_credit, mock_redis):
    sms = SMSService.create_sms(user_with_credit, '09121112233', 'Retry Test')

    from apps.sms.tasks import send_sms_task

    with patch('apps.sms.tasks.random.random', return_value=0.95):
        with patch('apps.sms.tasks.send_sms_task.retry') as mock_retry:
            mock_retry.side_effect = Exception('RetryTriggered')

            try:
                send_sms_task(str(sms.id))
            except Exception:
                pass

            assert mock_retry.called
            assert mock_retry.call_count == 1

    from apps.sms.services import SMSStatusBuffer
    assert mock_redis.llen(SMSStatusBuffer.KEY) == 1



def test_circuit_breaker_opens_after_failures(mock_redis):
    cb = CircuitBreaker("test_service", failure_threshold=3, recovery_timeout=10)

    assert not cb.is_open()

    cb.record_failure()
    cb.record_failure()
    cb.record_failure()

    assert cb.is_open()

    assert mock_redis.exists(cb._state_key)


def test_circuit_breaker_blocks_execution(user_with_credit, mock_redis):
    cb = CircuitBreaker("sms_provider_primary")
    cb.open_circuit()

    sms = SMSService.create_sms(user_with_credit, '09121112233', 'CB Test')

    from apps.sms.tasks import process_sms_sending

    with patch('apps.sms.tasks.process_sms_sending.retry') as mock_retry:
        mock_retry.side_effect = Exception('RetryLater')

        try:
            process_sms_sending(str(sms.id))
        except Exception:
            pass

        assert mock_retry.called



def test_rate_limiting(api_client, user):
    user.rate_limit_per_minute = 2
    user.save()
    pass


def test_full_sms_flow_integration(user_with_credit, mock_redis, settings):
    settings.SMS_COST_PER_MESSAGE = 10

    from apps.credits.services import CreditService
    initial_balance = CreditService.get_balance(user_with_credit)

    sms = SMSService.create_sms(user_with_credit, '09121112233', 'Full Flow')

    new_balance = CreditService.get_balance(user_with_credit)
    assert new_balance == initial_balance - Decimal('10')

    from apps.sms.services import SMSStatusBuffer
    SMSStatusBuffer.push_update(str(sms.id), 'sent')

    SMSStatusBuffer.flush_buffer()

    sms.refresh_from_db()
    assert sms.status == 'sent'

    CreditService.sync_deltas_to_db(user_with_credit.id)

    account = user_with_credit.credit_account
    account.refresh_from_db()
    assert account.total_spent >= Decimal('10')