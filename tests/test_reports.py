import pytest
from apps.sms.models import SMSMessage

pytestmark = pytest.mark.django_db


def test_sms_statistics_api(api_client, user_with_credit):
    SMSMessage.objects.create(user=user_with_credit, recipient='09121', status='sent', cost=10, message='1')
    SMSMessage.objects.create(user=user_with_credit, recipient='09122', status='sent', cost=10, message='2')
    SMSMessage.objects.create(user=user_with_credit, recipient='09123', status='failed', cost=10, message='3')
    SMSMessage.objects.create(user=user_with_credit, recipient='09124', status='queued', cost=10, message='4')

    api_client.credentials(HTTP_X_API_KEY=user_with_credit.api_key)

    response = api_client.get('/api/sms/statistics/')

    assert response.status_code == 200
    data = response.data

    assert data['total'] == 4
    assert data['sent'] == 2
    assert data['failed'] == 1
    assert data['pending'] == 1
    assert data['success_rate'] == 50.0


def test_sms_list_filtering(api_client, user_with_credit):
    SMSMessage.objects.create(user=user_with_credit, recipient='09121', status='sent', cost=10, message='A')
    SMSMessage.objects.create(user=user_with_credit, recipient='09122', status='failed', cost=10, message='B')

    api_client.credentials(HTTP_X_API_KEY=user_with_credit.api_key)

    response = api_client.get('/api/sms/messages/?status=sent')
    assert response.status_code == 200
    assert len(response.data['results']) == 1
    assert response.data['results'][0]['status'] == 'sent'

    response = api_client.get('/api/sms/messages/?status=failed')
    assert response.status_code == 200

    assert len(response.data['results']) == 1
    assert response.data['results'][0]['status'] == 'failed'