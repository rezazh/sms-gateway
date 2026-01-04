import pytest
from datetime import datetime
import pytz
from django.db import connection
from apps.sms.models import SMSMessage

pytestmark = pytest.mark.django_db


def test_sms_partitioning_routing(user_with_credit):
    date_2025 = datetime(2025, 6, 15, 12, 0, 0, tzinfo=pytz.UTC)
    date_2026 = datetime(2026, 6, 15, 12, 0, 0, tzinfo=pytz.UTC)

    sms_2025 = SMSMessage.objects.create(
        user=user_with_credit, recipient='09121111111', message='Msg 2025', cost=10
    )
    SMSMessage.objects.filter(id=sms_2025.id).update(created_at=date_2025)

    sms_2026 = SMSMessage.objects.create(
        user=user_with_credit, recipient='09122222222', message='Msg 2026', cost=10
    )
    SMSMessage.objects.filter(id=sms_2026.id).update(created_at=date_2026)

    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM sms_messages_y2025 WHERE id = %s", [str(sms_2025.id)])
        result_2025 = cursor.fetchone()[0]

        cursor.execute("SELECT count(*) FROM sms_messages_y2026 WHERE id = %s", [str(sms_2026.id)])
        result_2026 = cursor.fetchone()[0]

    assert result_2025 == 1, "SMS 2025 should be in partition y2025"
    assert result_2026 == 1, "SMS 2026 should be in partition y2026"