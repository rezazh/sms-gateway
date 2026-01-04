from decimal import Decimal

import pytest
import uuid

pytestmark = pytest.mark.django_db


@pytest.fixture
def user_with_credit(user, credit_service):
    credit_service.charge_account(user, 100, "Initial credit for API tests")
    return user


def test_send_sms_success(api_client, user_with_credit, mock_redis, settings):
    settings.SMS_COST_PER_MESSAGE = 10

    api_client.credentials(HTTP_X_API_KEY=user_with_credit.api_key)

    url = '/api/sms/send/'
    data = {
        'recipient': '09121112233',
        'message': 'This is a test message'
    }

    response = api_client.post(url, data, format='json')

    assert response.status_code == 202
    assert response.data['success'] is True
    assert 'sms_id' in response.data

    from apps.credits.services import CreditService
    balance = CreditService.get_balance(user_with_credit)
    assert balance == Decimal('90')

    assert mock_redis.llen("sms_ingest_buffer") == 1


def test_send_sms_insufficient_balance(api_client, user_with_credit):
    api_client.credentials(HTTP_X_API_KEY=user_with_credit.api_key)

    from apps.credits.services import CreditService
    CreditService.deduct_balance(user_with_credit, 100)

    url = '/api/sms/send/'
    data = {'recipient': '09121112233', 'message': 'This is a test message'}
    response = api_client.post(url, data, format='json')

    assert response.status_code == 400
    assert 'Insufficient balance' in response.data['error']


def test_send_sms_duplicate_request(api_client, user_with_credit):
    api_client.credentials(HTTP_X_API_KEY=user_with_credit.api_key)

    request_id = str(uuid.uuid4())
    headers = {'HTTP_X_REQUEST_ID': request_id}

    url = '/api/sms/send/'
    data = {'recipient': '09121112233', 'message': 'First request'}

    response1 = api_client.post(url, data, format='json', **headers)
    assert response1.status_code == 202

    response2 = api_client.post(url, data, format='json', **headers)
    assert response2.status_code == 409
    assert 'Duplicate request' in response2.data['error']