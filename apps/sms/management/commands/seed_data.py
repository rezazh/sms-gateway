from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.credits.services import CreditService
import hashlib

User = get_user_model()
STATIC_API_KEY = "XpDeksFh4e7sgmdLolghBL4f3a6L4TlLrlk5rtWBcUsUUfTjEi2533qK6QY5rdMO"
STATIC_HASH = hashlib.sha256(STATIC_API_KEY.encode()).hexdigest()


class Command(BaseCommand):
    help = 'Seeds database with test users and credit'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding data...')
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
            self.stdout.write('Created superuser: admin')

        user, _ = User.objects.get_or_create(username='heavy_user')
        user.set_password('pass123')
        user.api_key = STATIC_API_KEY
        user.rate_limit_per_minute = 10000
        user.api_key_hash = STATIC_HASH

        user.save()

        account = CreditService.get_or_create_account(user)
        account.balance = 0
        account.total_charged = 0
        account.total_spent = 0
        account.save()
        CreditService.charge_account(user, 10000000, "Reset huge charge for load test")
        self.stdout.write(f'Updated heavy_user with fixed API Key and 10M credit')

        user_norm, created = User.objects.get_or_create(username='normal_user')
        if created:
            user_norm.set_password('pass123')
            user_norm.save()
            CreditService.charge_account(user_norm, 5000, "Initial charge")
            self.stdout.write('Created normal_user with 5K credit')

        self.stdout.write(self.style.SUCCESS('Successfully seeded database'))