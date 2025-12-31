from django.test import TestCase
from django.contrib.auth import get_user_model
from decimal import Decimal
from .services import SMSService
from .models import SMSMessage
from apps.credits.services import CreditService

User = get_user_model()


class SMSServiceTestCase(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        CreditService.charge_account(self.user, 1000)

    def test_validate_phone_number_valid(self):
        phone = SMSService.validate_phone_number('09123456789')
        self.assertEqual(phone, '09123456789')

    def test_validate_phone_number_invalid(self):
        with self.assertRaises(ValueError):
            SMSService.validate_phone_number('123456789')

        with self.assertRaises(ValueError):
            SMSService.validate_phone_number('abc123')

    def test_calculate_sms_cost_normal(self):
        cost = SMSService.calculate_sms_cost('normal')
        self.assertEqual(cost, Decimal('0.10'))

    def test_calculate_sms_cost_express(self):
        cost = SMSService.calculate_sms_cost('express')
        self.assertEqual(cost, Decimal('0.20'))

    def test_create_sms(self):
        sms = SMSService.create_sms(
            user=self.user,
            recipient='09123456789',
            message='Test message',
            priority='normal'
        )
        self.assertIsNotNone(sms)
        self.assertEqual(sms.status, 'queued')
        self.assertEqual(sms.cost, Decimal('0.10'))
        self.assertEqual(sms.recipient, '09123456789')

    def test_create_sms_insufficient_balance(self):
        user2 = User.objects.create_user(
            username='pooruser',
            password='testpass123'
        )

        with self.assertRaises(ValueError) as context:
            SMSService.create_sms(
                user=user2,
                recipient='09123456789',
                message='Test message'
            )
        self.assertIn('Insufficient balance', str(context.exception))

    def test_create_sms_invalid_phone(self):
        with self.assertRaises(ValueError):
            SMSService.create_sms(
                user=self.user,
                recipient='123',
                message='Test message'
            )

    def test_create_sms_empty_message(self):
        with self.assertRaises(ValueError):
            SMSService.create_sms(
                user=self.user,
                recipient='09123456789',
                message=''
            )

    def test_cancel_message(self):
        sms = SMSService.create_sms(
            user=self.user,
            recipient='09123456789',
            message='Test message'
        )

        cancelled_sms = SMSService.cancel_message(sms.id, self.user)
        self.assertEqual(cancelled_sms.status, 'cancelled')

    def test_get_user_messages(self):
        SMSService.create_sms(
            user=self.user,
            recipient='09123456789',
            message='Test 1'
        )
        SMSService.create_sms(
            user=self.user,
            recipient='09123456789',
            message='Test 2'
        )

        messages = SMSService.get_user_messages(self.user)
        self.assertEqual(len(messages), 2)

    def test_get_statistics(self):
        SMSService.create_sms(
            user=self.user,
            recipient='09123456789',
            message='Test'
        )

        stats = SMSService.get_statistics(self.user)
        self.assertEqual(stats['total'], 1)
        self.assertEqual(stats['pending'], 1)