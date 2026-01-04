import pytest
from decimal import Decimal
import json

pytestmark = pytest.mark.django_db


@pytest.fixture
def sms_service():
    from apps.sms.services import SMSService
    return SMSService


@pytest.mark.parametrize("phone_number, is_valid", [
    ("09123456789", True),
    ("09351234567", True),
    (" 0912 345 6789 ", True),
    ("12345", False),
    ("091234567890", False),
    ("abcde", False),
    ("08123456789", False),
])
def test_validate_phone_number(sms_service, phone_number, is_valid):
    if is_valid:
        cleaned_phone = sms_service.validate_phone_number(phone_number)
        assert len(cleaned_phone) == 11
        assert cleaned_phone.isdigit()
    else:
        with pytest.raises(ValueError):
            sms_service.validate_phone_number(phone_number)


@pytest.mark.parametrize("priority, expected_cost", [
    ("normal", "0.10"),
    ("express", "0.20"),
])
def test_calculate_sms_cost(settings, sms_service, priority, expected_cost):
    settings.SMS_COST_PER_MESSAGE = 0.10
    settings.EXPRESS_MULTIPLIER = 2.0
    cost = sms_service.calculate_sms_cost(priority)
    assert cost == Decimal(expected_cost)


def test_queue_sms_for_ingest(sms_service, mock_redis):
    sms_data = {
        'id': 'some-uuid',
        'user_id': 1,
        'recipient': '09123456789',
        'message': 'hello'
    }
    sms_service.INGEST_BUFFER_KEY = 'test_ingest_buffer'

    sms_service.queue_sms_for_ingest(sms_data)

    assert mock_redis.llen(sms_service.INGEST_BUFFER_KEY) == 1
    queued_item = mock_redis.lpop(sms_service.INGEST_BUFFER_KEY)
    assert json.loads(queued_item) == sms_data