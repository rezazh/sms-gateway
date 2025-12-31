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

        # Create Heavy User (High Balance)
        user, created = User.objects.get_or_create(username='heavy_user')
        if created:
            user.set_password('pass123')
            user.rate_limit_per_minute = 1000  # High limit for load testing
            user.save()
            CreditService.charge_account(user, 10000000, "Initial huge charge")
            self.stdout.write('Created heavy_user with 10M credit')
        else:
            self.stdout.write('heavy_user already exists')

        # Create Normal User
        user_norm, created = User.objects.get_or_create(username='normal_user')
        if created:
            user_norm.set_password('pass123')
            user_norm.save()
            CreditService.charge_account(user_norm, 5000, "Initial charge")
            self.stdout.write('Created normal_user with 5K credit')
        else:
            self.stdout.write('normal_user already exists')

        self.stdout.write(self.style.SUCCESS('Successfully seeded database'))