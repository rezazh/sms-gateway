from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django_redis import get_redis_connection

from .models import SMSMessage
from apps.credits.services import CreditService
import logging
import json

logger = logging.getLogger(__name__)


class SMSService:
    INGEST_BUFFER_KEY = "sms_ingest_buffer"
    @staticmethod
    def calculate_sms_cost(priority='normal'):
        base_cost = Decimal(str(settings.SMS_COST_PER_MESSAGE))

        if priority == 'express':
            base_cost *= Decimal(str(settings.EXPRESS_MULTIPLIER))

        return base_cost

    @staticmethod
    def validate_phone_number(phone):
        phone = phone.replace(' ', '').replace('-', '')

        if not phone.isdigit():
            raise ValueError("Phone number must contain only digits")

        if len(phone) != 11 or not phone.startswith('09'):
            raise ValueError("Invalid phone number format. Must be 11 digits starting with 09")

        return phone

    @staticmethod
    def create_sms(user, recipient, message, priority='normal', scheduled_at=None):
        recipient = SMSService.validate_phone_number(recipient)

        if not message or len(message) == 0:
            raise ValueError("Message cannot be empty")

        if len(message) > 1000:
            raise ValueError("Message too long. Maximum 1000 characters")

        cost = SMSService.calculate_sms_cost(priority)

        CreditService.deduct_balance(user, cost)

        with transaction.atomic():
            sms = SMSMessage.objects.create(
                user=user,
                recipient=recipient,
                message=message,
                priority=priority,
                cost=cost,
                scheduled_at=scheduled_at,
                status='pending'
            )

        sms.status = 'queued'
        sms.save()

        logger.debug(
            f"SMS created - ID: {sms.id}, User: {user.username}, "
            f"Recipient: {recipient}, Cost: {cost}, Priority: {priority}"
        )

        from .tasks import send_sms_task
        if scheduled_at is None:
            queue_name = 'express_sms' if priority == 'express' else 'normal_sms'

            send_sms_task.apply_async(
                args=[str(sms.id)],
                queue=queue_name
            )

        return sms

    @staticmethod
    def get_user_messages(user, status=None, limit=100):
        queryset = SMSMessage.objects.filter(user=user).select_related('user')

        if status:
            queryset = queryset.filter(status=status)

        return queryset[:limit]

    @staticmethod
    def get_message_by_id(message_id, user=None):
        try:
            if user:
                return SMSMessage.objects.get(id=message_id, user=user)
            return SMSMessage.objects.get(id=message_id)
        except SMSMessage.DoesNotExist:
            return None

    @staticmethod
    def cancel_message(message_id, user):
        sms = SMSService.get_message_by_id(message_id, user)

        if not sms:
            raise ValueError("Message not found")

        if sms.status not in ['pending', 'queued']:
            raise ValueError("Cannot cancel message in current status")
        from django_redis import get_redis_connection
        cache_key = f"user_balance_{user.id}"
        redis_conn = get_redis_connection("default")
        redis_conn.incrbyfloat(cache_key, float(sms.cost))

        sms.status = 'cancelled'
        sms.save()

        return sms

    @staticmethod
    def get_statistics(user):
        total = SMSMessage.objects.filter(user=user).count()
        sent = SMSMessage.objects.filter(user=user, status='sent').count()
        failed = SMSMessage.objects.filter(user=user, status='failed').count()
        pending = SMSMessage.objects.filter(user=user, status__in=['pending', 'queued']).count()

        return {
            'total': total,
            'sent': sent,
            'failed': failed,
            'pending': pending,
            'success_rate': round((sent / total * 100) if total > 0 else 0, 2)
        }

    @staticmethod
    def queue_sms_for_ingest(sms_data):
        redis_conn = get_redis_connection("default")
        redis_conn.rpush(SMSService.INGEST_BUFFER_KEY, json.dumps(sms_data))

    @staticmethod
    def process_ingest_buffer(batch_size=5000):
        redis_conn = get_redis_connection("default")

        try:
            raw_items = redis_conn.lpop(SMSService.INGEST_BUFFER_KEY, batch_size)
        except Exception:
            return 0

        if not raw_items:
            return 0

        sms_objects = []
        task_payloads = []

        try:
            for item in raw_items:
                if isinstance(item, bytes):
                    item = item.decode('utf-8')

                data = json.loads(item)
                sms = SMSMessage(
                    id=data['id'],
                    user_id=data['user_id'],
                    recipient=data['recipient'],
                    message=data['message'],
                    priority=data['priority'],
                    cost=Decimal(data['cost']),
                    scheduled_at=data.get('scheduled_at'),
                    status='queued'
                )
                sms_objects.append(sms)

                if not sms.scheduled_at:
                    task_payloads.append({'id': str(sms.id), 'priority': sms.priority})

            if sms_objects:
                SMSMessage.objects.bulk_create(sms_objects, batch_size=batch_size, ignore_conflicts=True)

                from .tasks import send_sms_task
                for payload in task_payloads:
                    queue = 'express_sms' if payload['priority'] == 'express' else 'normal_sms'
                    send_sms_task.apply_async(args=[payload['id']], queue=queue)

        except Exception as e:
            logger.error(f"CRITICAL: Failed to ingest batch. Pushing back to Redis. Error: {e}")
            if raw_items:
                redis_conn.rpush(SMSService.INGEST_BUFFER_KEY, *raw_items)
            raise e

        return len(sms_objects)


class SMSStatusBuffer:
    KEY = "sms_status_buffer"

    @staticmethod
    def push_update(sms_id, status, failed_reason=""):
        data = json.dumps({
            'id': str(sms_id),
            'status': status,
            'reason': failed_reason
        })
        redis_conn = get_redis_connection("default")
        redis_conn.rpush(SMSStatusBuffer.KEY, data)

    @staticmethod
    def flush_buffer():
        redis_conn = get_redis_connection("default")
        items = redis_conn.lpop(SMSStatusBuffer.KEY, 1000)

        if not items:
            return

        updates = {}
        for item in items:
            try:
                if isinstance(item, bytes):
                    item = item.decode('utf-8')

                data = json.loads(item)
                sms_id = data['id']
                updates[sms_id] = {'status': data['status'], 'reason': data['reason']}
            except Exception as e:
                logger.error(f"Error parsing buffer item: {e}")
                continue

        if updates:
            from .models import SMSMessage
            sms_list = SMSMessage.objects.filter(id__in=updates.keys())

            to_update = []
            for sms in sms_list:
                data = updates[str(sms.id)]
                sms.status = data['status']
                if data['reason']:
                    sms.failed_reason = data['reason']
                to_update.append(sms)

            SMSMessage.objects.bulk_update(to_update, ['status', 'failed_reason'], batch_size=1000)
            logger.info(f"Bulk updated {len(to_update)} SMS statuses from buffer.")
            return len(to_update)
        return 0