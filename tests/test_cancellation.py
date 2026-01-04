import pytest
from decimal import Decimal
from apps.sms.services import SMSService
from apps.credits.services import CreditService

pytestmark = pytest.mark.django_db


def test_cancel_queued_sms_refunds_credit(api_client, user_with_credit, mock_redis):
    initial_balance = CreditService.get_balance(user_with_credit)

    sms = SMSService.create_sms(
        user=user_with_credit,
        recipient='09121112233',
        message='To be cancelled'
    )

    balance_after_send = CreditService.get_balance(user_with_credit)
    assert balance_after_send == initial_balance - sms.cost

    api_client.credentials(HTTP_X_API_KEY=user_with_credit.api_key)
    url = f'/api/sms/messages/{sms.id}/cancel/'

    response = api_client.post(url)
    assert response.status_code == 200
    assert response.data['status'] == 'cancelled'

    final_balance = CreditService.get_balance(user_with_credit)
    assert final_balance == initial_balance

    sms.refresh_from_db()
    assert sms.status == 'cancelled'


def test_cannot_cancel_sent_sms(api_client, user_with_credit):
    sms = SMSService.create_sms(
        user=user_with_credit,
        recipient='09121112233',
        message='Already sent'
    )
    sms.status = 'sent'
    sms.save()

    api_client.credentials(HTTP_X_API_KEY=user_with_credit.api_key)
    url = f'/api/sms/messages/{sms.id}/cancel/'

    response = api_client.post(url)
    assert response.status_code == 400