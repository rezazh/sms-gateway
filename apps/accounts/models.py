from django.contrib.auth.models import AbstractUser
from django.db import models
import secrets
import hashlib


class User(AbstractUser):
    api_key_hash = models.CharField(max_length=64, unique=True, db_index=True, blank=True)
    is_active = models.BooleanField(default=True)
    rate_limit_per_minute = models.IntegerField(default=100)

    class Meta:
        db_table = 'users'

    def save(self, *args, **kwargs):
        if not self.pk and not self.api_key_hash:
            raw_key = secrets.token_urlsafe(48)
            self.api_key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
            self._raw_api_key = raw_key
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username