from drf_spectacular.types import OpenApiTypes
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter
from .services import CreditService
from .serializers import (
    CreditAccountSerializer,
    CreditTransactionSerializer,
    ChargeAccountSerializer
)


class CreditBalanceView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Credits'],
        summary='Get credit balance',
        description='Get current credit balance for authenticated user',
        responses={
            200: CreditAccountSerializer,
        }
    )
    def get(self, request):
        account = CreditService.get_or_create_account(request.user)
        serializer = CreditAccountSerializer(account)
        return Response(serializer.data)


class ChargeAccountView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Credits'],
        summary='Charge account',
        description='Add credit to user account',
        request=ChargeAccountSerializer,
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'success': {'type': 'boolean'},
                    'message': {'type': 'string'},
                    'balance': {'type': 'string'}
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
        serializer = ChargeAccountSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            account = CreditService.charge_account(
                user=request.user,
                amount=serializer.validated_data['amount'],
                description=serializer.validated_data.get('description', '')
            )

            return Response(
                {
                    'success': True,
                    'message': 'Account charged successfully',
                    'balance': str(account.balance)
                },
                status=status.HTTP_200_OK
            )
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class CreditTransactionsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Credits'],
        summary='Get transactions',
        description='Get list of credit transactions for authenticated user',
        parameters=[
            OpenApiParameter(
                name='limit',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='Maximum number of transactions to return',
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
                        'items': {'$ref': '#/components/schemas/CreditTransaction'}
                    }
                }
            }
        }
    )
    def get(self, request):
        limit = int(request.query_params.get('limit', 100))
        transactions = CreditService.get_transactions(request.user, limit=limit)
        serializer = CreditTransactionSerializer(transactions, many=True)

        return Response({
            'count': len(serializer.data),
            'results': serializer.data
        })