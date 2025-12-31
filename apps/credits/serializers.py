from rest_framework import serializers
from .models import CreditAccount, CreditTransaction


class CreditAccountSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = CreditAccount
        fields = ['username', 'balance', 'total_charged', 'total_spent', 'created_at', 'updated_at']
        read_only_fields = ['balance', 'total_charged', 'total_spent', 'created_at', 'updated_at']


class CreditTransactionSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='account.user.username', read_only=True)

    class Meta:
        model = CreditTransaction
        fields = [
            'id', 'username', 'transaction_type', 'amount',
            'balance_before', 'balance_after', 'description',
            'reference_id', 'created_at'
        ]
        read_only_fields = fields


class ChargeAccountSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)
    description = serializers.CharField(required=False, allow_blank=True, max_length=500)