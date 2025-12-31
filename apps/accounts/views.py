from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import connection
from django.core.cache import cache
from drf_spectacular.utils import extend_schema
import redis


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
            'services': {}
        }

        try:
            connection.ensure_connection()
            health_status['services']['database'] = 'healthy'
        except Exception as e:
            health_status['services']['database'] = f'unhealthy: {str(e)}'
            health_status['status'] = 'unhealthy'

        try:
            cache.set('health_check', 'ok', 10)
            if cache.get('health_check') == 'ok':
                health_status['services']['redis'] = 'healthy'
            else:
                health_status['services']['redis'] = 'unhealthy'
                health_status['status'] = 'unhealthy'
        except Exception as e:
            health_status['services']['redis'] = f'unhealthy: {str(e)}'
            health_status['status'] = 'unhealthy'

        try:
            from config.celery import app
            inspect = app.control.inspect()
            active = inspect.active()
            if active:
                health_status['services']['celery'] = 'healthy'
            else:
                health_status['services']['celery'] = 'no workers'
                health_status['status'] = 'degraded'
        except Exception as e:
            health_status['services']['celery'] = f'unhealthy: {str(e)}'
            health_status['status'] = 'unhealthy'

        status_code = status.HTTP_200_OK
        if health_status['status'] == 'unhealthy':
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        elif health_status['status'] == 'degraded':
            status_code = status.HTTP_200_OK

        return Response(health_status, status=status_code)