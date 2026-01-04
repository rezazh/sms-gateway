import pytest
from django.utils import timezone
from datetime import timedelta
from apps.sms.services import SMSService
from apps.sms.models import SMSMessage
from unittest.mock import patch

pytestmark = pytest.mark.django_db


def test_future_sms_scheduling(user_with_credit, mock_redis):
    future_time = timezone.now() + timedelta(hours=1)

    sms = SMSService.create_sms(
        user=user_with_credit,
        recipient='09121112233',
        message='Future Message',
        scheduled_at=future_time
    )

    assert sms.status == 'queued'

    from apps.sms.tasks import process_scheduled_sms

    with patch('apps.sms.tasks.send_sms_task.delay') as mock_send:
        process_scheduled_sms()
        mock_send.assert_not_called()

    past_time = timezone.now() - timedelta(minutes=1)
    SMSMessage.objects.filter(id=sms.id).update(scheduled_at=past_time)

    with patch('apps.sms.tasks.send_sms_task.delay') as mock_send:
        result = process_scheduled_sms()

        assert result['processed'] == 1
        mock_send.assert_called_once_with(str(sms.id))
        