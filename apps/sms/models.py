from django.db import models
from django.conf import settings
from decimal import Decimal
import uuid


class SMSMessage(models.Model):

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('queued', 'Queued'),
        ('sending', 'Sending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    PRIORITY_CHOICES = [
        ('normal', 'Normal'),
        ('express', 'Express'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sms_messages'
    )
    recipient = models.CharField(
        max_length=15,
        help_text="Recipient phone number"
    )
    message = models.TextField(
        max_length=1000,
        help_text="SMS message text"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='normal'
    )
    cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Cost of sending"
    )
    scheduled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Scheduled send time"
    )
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Actual send time"
    )
    failed_reason = models.TextField(
        blank=True,
        help_text="Failure reason"
    )
    retry_count = models.IntegerField(
        default=0,
        help_text="Number of retry attempts"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sms_messages'
        verbose_name = 'SMS Message'
        verbose_name_plural = 'SMS Messages'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['recipient']),
            models.Index(
                fields=['scheduled_at'],
                name='sms_pending_schedule_idx',
                condition=models.Q(status='queued')
            ),
        ]

    def __str__(self):
        return f"{self.recipient} - {self.status}"

    def calculate_cost(self):
        base_cost = Decimal(str(settings.SMS_COST_PER_MESSAGE))

        if self.priority == 'express':
            base_cost *= Decimal(str(settings.EXPRESS_MULTIPLIER))

        return base_cost

    def mark_as_sent(self):
        from django.utils import timezone
        self.status = 'sent'
        self.sent_at = timezone.now()
        self.save()

    def mark_as_failed(self, reason):
        self.status = 'failed'
        self.failed_reason = reason
        self.retry_count += 1
        self.save()

    def can_retry(self, max_retries=3):
        return self.retry_count < max_retries