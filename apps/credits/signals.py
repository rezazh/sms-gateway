from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import CreditAccount


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_credit_account(sender, instance, created, **kwargs):
    if created:
        CreditAccount.objects.create(user=instance)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def save_credit_account(sender, instance, **kwargs):
    if hasattr(instance, 'credit_account'):
        instance.credit_account.save()