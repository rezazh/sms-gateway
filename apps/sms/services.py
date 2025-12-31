from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import SMSMessage
from apps.credits.services import CreditService
import logging

logger = logging.getLogger(__name__)


class SMSService:
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

        CreditService.deduct_balance_cache(user, cost)

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

        logger.info(
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
        queryset = SMSMessage.objects.filter(user=user)

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