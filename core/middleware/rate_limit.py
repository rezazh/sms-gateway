import time
from django.http import JsonResponse
from rest_framework import status
from django_redis import get_redis_connection


class RateLimitMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith('/api/') or request.path.startswith('/health/'):
            return self.get_response(request)

        if hasattr(request, 'user') and request.user.is_authenticated:
            ident = f"user_{request.user.id}"
            limit = request.user.rate_limit_per_minute
        else:
            ip = self.get_client_ip(request)
            ident = f"ip_{ip}"
            limit = 20

        if self.is_rate_limited(ident, limit):
            return JsonResponse(
                {
                    'error': 'Too Many Requests',
                    'detail': f'Rate limit exceeded. Maximum {limit} requests per minute.',
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        return self.get_response(request)

    def is_rate_limited(self, ident, limit):
        redis_conn = get_redis_connection("default")
        key = f"ratelimit:sliding:{ident}"
        now = time.time()
        window_start = now - 60

        try:
            pipeline = redis_conn.pipeline()

            pipeline.zremrangebyscore(key, 0, window_start)

            pipeline.zadd(key, {f"{now}": now})

            pipeline.zcard(key)

            pipeline.expire(key, 120)

            results = pipeline.execute()

            request_count = results[2]

            if request_count > limit:
                redis_conn.zrem(key, f"{now}")
                return True

            return False

        except Exception as e:
            print(f"Rate limit error: {e}")
            return False

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip