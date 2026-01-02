from django_redis import get_redis_connection
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from core.pagination import FastPagination
from .services import SMSService
from .serializers import (
    SMSMessageSerializer,
    CreateSMSSerializer,
    SMSStatisticsSerializer
)
import uuid

class SendSMSView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['SMS'],
        summary='Send SMS',
        description='Queue SMS message for sending',
        request=CreateSMSSerializer,
        responses={
            201: {
                'type': 'object',
                'properties': {
                    'success': {'type': 'boolean'},
                    'message': {'type': 'string'},
                    'sms_id': {'type': 'string', 'format': 'uuid'},
                    'cost': {'type': 'string'},
                    'status': {'type': 'string'}
                }
            },
            400: {
                'type': 'object',
                'properties': {
                    'error': {'type': 'string'}
                }
            }
        }
    )
    def post(self, request):
        request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
        redis_conn = get_redis_connection("default")
        idempotency_key = f"idempotency:{request.user.id}:{request_id}"
        if not redis_conn.setnx(idempotency_key, "processing"):
            return Response({"error": "Duplicate request"}, status=409)
        redis_conn.expire(idempotency_key, 86400)

        data = request.data
        recipient = data.get('recipient')
        message = data.get('message')
        priority = data.get('priority', 'normal')
        scheduled_at = data.get('scheduled_at')

        try:
            if not recipient or not message:
                raise ValueError("Recipient and message are required")

            recipient = SMSService.validate_phone_number(recipient)
            cost = SMSService.calculate_sms_cost(priority)

            from apps.credits.services import CreditService
            CreditService.deduct_balance(request.user, cost)

            sms_id = str(uuid.uuid4())
            sms_payload = {
                'id': sms_id,
                'user_id': request.user.id,
                'recipient': recipient,
                'message': message,
                'priority': priority,
                'cost': str(cost),
                'scheduled_at': scheduled_at
            }

            SMSService.queue_sms_for_ingest(sms_payload)

            return Response(
                {
                    'success': True,
                    'message': 'SMS queued successfully',
                    'sms_id': sms_id,
                    'cost': str(cost),
                    'status': 'queued'
                },
                status=status.HTTP_202_ACCEPTED
            )

        except ValueError as e:
            redis_conn.delete(idempotency_key)
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            redis_conn.delete(idempotency_key)
            return Response({'error': 'Internal error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SMSListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['SMS'],
        summary='List SMS messages',
        description='Get list of SMS messages for authenticated user',
        parameters=[
            OpenApiParameter(
                name='status',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Filter by status',
                enum=['pending', 'queued', 'sending', 'sent', 'failed', 'cancelled']
            ),
            OpenApiParameter(
                name='limit',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='Maximum number of messages to return',
                default=100
            )
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'count': {'type': 'integer'},
                    'results': {
                        'type': 'array',
                        'items': {'$ref': '#/components/schemas/SMSMessage'}
                    }
                }
            }
        }
    )
    def get(self, request):
        status_filter = request.query_params.get('status')
        limit = int(request.query_params.get('limit', 100))

        messages = SMSService.get_user_messages(
            user=request.user,
            status=status_filter,
            limit=limit
        )


        paginator = FastPagination()
        paginated_messages = paginator.paginate_queryset(messages, request)
        serializer = SMSMessageSerializer(paginated_messages, many=True)

        return paginator.get_paginated_response(serializer.data)


class SMSDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['SMS'],
        summary='Get SMS detail',
        description='Get details of a specific SMS message',
        responses={
            200: SMSMessageSerializer,
            404: {
                'type': 'object',
                'properties': {
                    'error': {'type': 'string'}
                }
            }
        }
    )
    def get(self, request, message_id):
        sms = SMSService.get_message_by_id(message_id, request.user)

        if not sms:
            return Response(
                {'error': 'Message not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = SMSMessageSerializer(sms)
        return Response(serializer.data)


class CancelSMSView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['SMS'],
        summary='Cancel SMS',
        description='Cancel a pending or queued SMS message',
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'success': {'type': 'boolean'},
                    'message': {'type': 'string'},
                    'sms_id': {'type': 'string', 'format': 'uuid'},
                    'status': {'type': 'string'}
                }
            },
            400: {
                'type': 'object',
                'properties': {
                    'error': {'type': 'string'}
                }
            }
        }
    )
    def post(self, request, message_id):
        try:
            sms = SMSService.cancel_message(message_id, request.user)

            return Response(
                {
                    'success': True,
                    'message': 'SMS cancelled successfully',
                    'sms_id': str(sms.id),
                    'status': sms.status
                },
                status=status.HTTP_200_OK
            )
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class SMSStatisticsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['SMS'],
        summary='Get statistics',
        description='Get SMS statistics for authenticated user',
        responses={
            200: SMSStatisticsSerializer
        }
    )
    def get(self, request):
        stats = SMSService.get_statistics(request.user)
        serializer = SMSStatisticsSerializer(stats)
        return Response(serializer.data)