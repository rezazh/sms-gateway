from django.conf import settings
from django_redis import get_redis_connection
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
import json
import uuid
import logging
from drf_spectacular.types import OpenApiTypes

from .serializers import CreateSMSSerializer, SMSMessageSerializer, SMSStatisticsSerializer
from .services import SMSService
from core.pagination import FastPagination
from apps.credits.services import CreditService
from drf_spectacular.utils import extend_schema, OpenApiParameter

logger = logging.getLogger(__name__)


class SendSMSView(APIView):
    permission_classes = [IsAuthenticated]

    DEDUCT_SCRIPT = """
        local balance = tonumber(redis.call('get', KEYS[1]))
        if not balance then return -2 end
        local amount = tonumber(ARGV[1])
        if balance < amount then return -1 end
        redis.call('incrbyfloat', KEYS[1], -amount)
        redis.call('incrbyfloat', KEYS[2], amount)
        return 1
    """

    @extend_schema(
        tags=['SMS'],
        summary='Send SMS (High-Performance)',
        request=CreateSMSSerializer,
        responses={202: None}
    )
    def post(self, request):
        serializer = CreateSMSSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        user = request.user
        user_id = user.id

        try:
            recipient = SMSService.validate_phone_number(data['recipient'])
            cost = SMSService.calculate_sms_cost(data['priority'])
            sms_id = str(uuid.uuid4())
            request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))

            idempotency_key = f"idempotency:{user_id}:{request_id}"
            balance_key = f"user_balance_{user_id}"
            pending_key = f"pending_deduct_{user_id}"

            r = get_redis_connection("default")

            if not r.set(idempotency_key, "processing", nx=True):
                return Response({"error": "Duplicate request"}, status=status.HTTP_409_CONFLICT)

            r.expire(idempotency_key, 86400)

            deduct_script = r.register_script(self.DEDUCT_SCRIPT)
            deduct_result = deduct_script(keys=[balance_key, pending_key], args=[float(cost)])

            if deduct_result == -1:
                r.delete(idempotency_key)
                return Response({'error': 'Insufficient balance'}, status=status.HTTP_400_BAD_REQUEST)

            elif deduct_result == -2:
                CreditService.get_balance(user)
                deduct_result = deduct_script(keys=[balance_key, pending_key], args=[float(cost)])
                if deduct_result == -1:
                    r.delete(idempotency_key)
                    return Response({'error': 'Insufficient balance'}, status=status.HTTP_400_BAD_REQUEST)

            sms_payload = {
                'id': sms_id, 'user_id': user_id, 'recipient': recipient,
                'message': data['message'], 'priority': data['priority'],
                'cost': str(cost),
                'scheduled_at': data.get('scheduled_at').isoformat() if data.get('scheduled_at') else None
            }
            r.rpush("sms_ingest_buffer", json.dumps(sms_payload))

            return Response({
                'success': True, 'message': 'SMS queued successfully',
                'sms_id': sms_id, 'cost': str(cost), 'status': 'queued'
            }, status=status.HTTP_202_ACCEPTED)

        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error in SendSMS: {e}", exc_info=True)
            return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
        responses={200: SMSMessageSerializer}
    )
    def get(self, request, message_id):
        sms = SMSService.get_message_by_id(message_id, request.user)
        if not sms:
            return Response({'error': 'Message not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = SMSMessageSerializer(sms)
        return Response(serializer.data)


class CancelSMSView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['SMS'],
        summary='Cancel SMS',
        responses={200: dict}
    )
    def post(self, request, message_id):
        try:
            sms = SMSService.cancel_message(message_id, request.user)
            return Response({
                'success': True,
                'message': 'SMS cancelled successfully',
                'sms_id': str(sms.id),
                'status': sms.status
            }, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class SMSStatisticsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['SMS'],
        summary='Get statistics',
        responses={200: SMSStatisticsSerializer}
    )
    def get(self, request):
        stats = SMSService.get_statistics(request.user)
        serializer = SMSStatisticsSerializer(stats)
        return Response(serializer.data)