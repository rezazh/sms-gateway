from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.cache import cache
from decimal import Decimal
from .services import CreditService
from .models import CreditAccount, CreditTransaction

User = get_user_model()


class CreditServiceTestCase(TestCase):

    def setUp(self):
        cache.clear()

        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.account = CreditService.get_or_create_account(self.user)

    def test_get_or_create_account(self):
        account = CreditService.get_or_create_account(self.user)
        self.assertIsNotNone(account)
        self.assertEqual(account.balance, Decimal('0.00'))

        cached_balance = CreditService.get_balance_cache(self.user)
        self.assertEqual(cached_balance, Decimal('0.00'))

    def test_charge_account(self):
        CreditService.charge_account(
            user=self.user,
            amount=1000,
            description="Test charge"
        )

        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal('1000.00'))

        cached_balance = CreditService.get_balance_cache(self.user)
        self.assertEqual(cached_balance, Decimal('1000.00'))

    def test_deduct_account_cache(self):
        CreditService.charge_account(self.user, 1000)

        result = CreditService.deduct_balance_cache(self.user, 500)
        self.assertTrue(result)

        cached_balance = CreditService.get_balance_cache(self.user)
        self.assertEqual(cached_balance, Decimal('500.00'))

        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal('1000.00'))

    def test_deduct_insufficient_balance(self):
        CreditService.charge_account(self.user, 100)

        with self.assertRaises(ValueError):
            CreditService.deduct_balance_cache(self.user, 200)

    def test_sync_to_db(self):
        CreditService.charge_account(self.user, 1000)

        CreditService.deduct_balance_cache(self.user, 300)

        cached = CreditService.get_balance_cache(self.user)  # 700
        self.account.refresh_from_db()  # 1000
        self.assertNotEqual(cached, self.account.balance)

        CreditService.sync_balance_to_db(self.user.id)

        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal('700.00'))