from django.db import models
from django.conf import settings
from decimal import Decimal


class CreditAccount(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='credit_account'
    )
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Current balance in Toman"
    )
    total_charged = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total amount charged"
    )
    total_spent = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total amount spent"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'credit_accounts'
        verbose_name = 'Credit Account'
        verbose_name_plural = 'Credit Accounts'

    def __str__(self):
        return f"{self.user.username} - Balance: {self.balance}"

    def charge(self, amount):
        if amount <= 0:
            raise ValueError("Charge amount must be positive")

        self.balance += Decimal(str(amount))
        self.total_charged += Decimal(str(amount))
        self.save()
        return self.balance

    def deduct(self, amount):
        if amount <= 0:
            raise ValueError("Deduction amount must be positive")

        if self.balance < Decimal(str(amount)):
            raise ValueError("Insufficient balance")

        self.balance -= Decimal(str(amount))
        self.total_spent += Decimal(str(amount))
        self.save()
        return self.balance

    def has_sufficient_balance(self, amount):
        return self.balance >= Decimal(str(amount))


class CreditTransaction(models.Model):

    TRANSACTION_TYPE_CHOICES = [
        ('charge', 'Charge'),
        ('deduct', 'Deduct'),
        ('refund', 'Refund'),
    ]

    account = models.ForeignKey(
        CreditAccount,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    transaction_type = models.CharField(
        max_length=10,
        choices=TRANSACTION_TYPE_CHOICES
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )
    balance_before = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Balance before transaction"
    )
    balance_after = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Balance after transaction"
    )
    description = models.TextField(blank=True)
    reference_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Reference ID (e.g., SMS message ID)"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'credit_transactions'
        verbose_name = 'Credit Transaction'
        verbose_name_plural = 'Credit Transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['account', '-created_at']),
            models.Index(fields=['reference_id']),
        ]

    def __str__(self):
        return f"{self.account.user.username} - {self.transaction_type} - {self.amount}"