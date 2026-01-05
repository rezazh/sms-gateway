from rest_framework import authentication
from rest_framework import exceptions
from django.contrib.auth import get_user_model
import hashlib

User = get_user_model()


class APIKeyAuthentication(authentication.BaseAuthentication):

    def authenticate(self, request):
        raw_api_key = request.headers.get('X-Api-Key')

        if not raw_api_key:
            return None

        hashed_key = hashlib.sha256(raw_api_key.encode()).hexdigest()

        try:
            user = User.objects.only('api_key').get(api_key=hashed_key)
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid API key')

        return (user, None)