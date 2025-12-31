from django.core.cache import cache
from django.http import JsonResponse
from rest_framework import status
from django_redis import get_redis_connection
import time


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
            ident = f"ip_{self.get_client_ip(request)}"
            limit = 10


        current_minute = int(time.time() / 60)
        cache_key = f"ratelimit:{ident}:{current_minute}"

        try:
            redis_conn = get_redis_connection("default")
            pipeline = redis_conn.pipeline()
            pipeline.incr(cache_key)
            pipeline.expire(cache_key, 60)
            result = pipeline.execute()

            request_count = result[0]

            if request_count > limit:
                return JsonResponse(
                    {
                        'error': 'Too Many Requests',
                        'detail': f'Rate limit exceeded. Maximum {limit} requests per minute.',
                    },
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )

            response = self.get_response(request)

            response['X-RateLimit-Limit'] = str(limit)
            response['X-RateLimit-Remaining'] = str(max(0, limit - request_count))
            response['X-RateLimit-Reset'] = str((current_minute + 1) * 60)

            return response

        except Exception as e:
            print(f"Rate limit error: {e}")
            return self.get_response(request)

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip