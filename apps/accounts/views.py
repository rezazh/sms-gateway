from django_redis import get_redis_connection
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import connection
from django.core.cache import cache
from drf_spectacular.utils import extend_schema
import redis

from apps.sms.services import SMSStatusBuffer


class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        tags=['Health'],
        summary='Health check',
        description='Check health status of all system components',
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'status': {'type': 'string', 'enum': ['healthy', 'degraded', 'unhealthy']},
                    'services': {
                        'type': 'object',
                        'properties': {
                            'database': {'type': 'string'},
                            'redis': {'type': 'string'},
                            'celery': {'type': 'string'}
                        }
                    }
                }
            },
            503: {
                'type': 'object',
                'properties': {
                    'status': {'type': 'string'},
                    'services': {'type': 'object'}
                }
            }
        }
    )
    def get(self, request):
        health_status = {
            'status': 'healthy',
            'components': {}
        }

        has_error = False
        is_degraded = False

        try:
            connection.ensure_connection()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            health_status['components']['database'] = 'ok'
        except Exception as e:
            health_status['components']['database'] = f'error: {str(e)}'
            has_error = True

        try:
            redis_conn = get_redis_connection("default")
            redis_conn.ping()
            health_status['components']['redis'] = 'ok'
        except Exception as e:
            health_status['components']['redis'] = f'error: {str(e)}'
            has_error = True

        try:
            redis_conn = get_redis_connection("default")
            buffer_size = redis_conn.llen(SMSStatusBuffer.KEY)
            health_status['components']['sms_buffer_size'] = buffer_size

            if buffer_size > 10000:
                is_degraded = True
                health_status['components']['sms_buffer_status'] = 'warning: high backlog'
            else:
                health_status['components']['sms_buffer_status'] = 'ok'

        except Exception:
            pass

        try:
            celery_status = cache.get('health_celery_status')
            if not celery_status:
                from config.celery import app
                i = app.control.inspect(timeout=0.5)
                active_workers = i.active()

                if active_workers:
                    celery_status = 'ok'
                    cache.set('health_celery_status', 'ok', 10)
                else:
                    celery_status = 'no workers found'
                    is_degraded = True

            health_status['components']['celery'] = celery_status

        except Exception as e:
            health_status['components']['celery'] = f'warning: {str(e)}'
            is_degraded = True

        if has_error:
            health_status['status'] = 'unhealthy'
            return Response(health_status, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        elif is_degraded:
            health_status['status'] = 'degraded'
            return Response(health_status, status=status.HTTP_200_OK)
        else:
            return Response(health_status, status=status.HTTP_200_OK)