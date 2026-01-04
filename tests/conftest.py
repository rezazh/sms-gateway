import pytest
from fakeredis import FakeStrictRedis, FakeServer
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.credits.models import CreditAccount
from apps.credits.services import CreditService
from apps.sms.services import SMSService

User = get_user_model()


@pytest.fixture(scope='session')
def django_db_setup(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        pass


@pytest.fixture
def user(db):
    return User.objects.create_user(username='test_user', password='password123')


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def credit_account(db, user):
    account, created = CreditAccount.objects.get_or_create(user=user)
    account.balance = 1000
    account.total_charged = 1000
    account.save()
    return account


@pytest.fixture
def user_with_credit(user, credit_service):
    credit_service.charge_account(user, 100, "Initial credit for API tests")
    return user


@pytest.fixture
def mock_redis(monkeypatch):
    server = FakeServer(version=7)
    fake_redis_instance = FakeStrictRedis(server=server, decode_responses=True)

    def mock_get_redis_connection(*args, **kwargs):
        return fake_redis_instance

    monkeypatch.setattr("django_redis.get_redis_connection", mock_get_redis_connection)

    monkeypatch.setattr("apps.credits.services.get_redis_connection", mock_get_redis_connection)
    monkeypatch.setattr("apps.sms.services.get_redis_connection", mock_get_redis_connection)

    monkeypatch.setattr("apps.sms.views.get_redis_connection", mock_get_redis_connection)
    monkeypatch.setattr("core.utils.get_redis_connection", mock_get_redis_connection)
    yield fake_redis_instance
    fake_redis_instance.flushall()


@pytest.fixture
def credit_service():
    return CreditService


@pytest.fixture
def sms_service():
    return SMSService