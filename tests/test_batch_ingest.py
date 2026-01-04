import pytest
import json
from decimal import Decimal
from apps.sms.services import SMSService
from apps.sms.models import SMSMessage

pytestmark = pytest.mark.django_db


def test_batch_ingest_process(user_with_credit, mock_redis):
    sms_service = SMSService

    buffer_key = sms_service.INGEST_BUFFER_KEY
    messages_to_create = []

    for i in range(10):
        sms_data = {
            'id': f'00000000-0000-0000-0000-00000000000{i}',
            'user_id': user_with_credit.id,
            'recipient': f'0912000000{i}',
            'message': f'Test Message {i}',
            'priority': 'normal',
            'cost': '10.00',
            'scheduled_at': None
        }
        messages_to_create.append(json.dumps(sms_data))

    mock_redis.rpush(buffer_key, *messages_to_create)

    assert mock_redis.llen(buffer_key) == 10

    processed_count = sms_service.process_ingest_buffer(batch_size=5)

    assert processed_count == 5
    assert mock_redis.llen(buffer_key) == 5

    assert SMSMessage.objects.count() == 5
    assert SMSMessage.objects.filter(recipient='09120000000').exists()

    processed_count_2 = sms_service.process_ingest_buffer(batch_size=100)
    assert processed_count_2 == 5
    assert mock_redis.llen(buffer_key) == 0
    assert SMSMessage.objects.count() == 10