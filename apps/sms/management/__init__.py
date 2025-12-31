from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.credits.services import CreditService
import random

User = get_user_model()


class Command(BaseCommand):
    help = 'Seeds database with test users and credit'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding data...')

        # Create Admin
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
            self.stdout.write('Created superuser: admin')

        # Create Heavy User
        user, created = User.objects.get_or_create(username='heavy_user')
        user.set_password('pass123')
        user.save()

        if created:
            CreditService.charge_account(user, 10000000, "Initial huge charge")
            self.stdout.write('Created heavy_user with 10M credit')

        # Create Normal User
        user_norm, created = User.objects.get_or_create(username='normal_user')
        user_norm.set_password('pass123')
        user_norm.save()

        if created:
            CreditService.charge_account(user_norm, 5000, "Initial charge")
            self.stdout.write('Created normal_user with 5K credit')

        self.stdout.write(self.style.SUCCESS('Successfully seeded database'))