from rest_framework import serializers
from .models import SMSMessage


class SMSMessageSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = SMSMessage
        fields = [
            'id', 'username', 'recipient', 'message', 'status',
            'priority', 'cost', 'scheduled_at', 'sent_at',
            'failed_reason', 'retry_count', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'username', 'status', 'cost', 'sent_at',
            'failed_reason', 'retry_count', 'created_at', 'updated_at'
        ]


class CreateSMSSerializer(serializers.Serializer):
    recipient = serializers.CharField(max_length=15)
    message = serializers.CharField(max_length=1000)
    priority = serializers.ChoiceField(choices=['normal', 'express'], default='normal')
    scheduled_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate_recipient(self, value):
        from apps.sms.services import SMSService
        return SMSService.validate_phone_number(value)


class SMSStatisticsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    sent = serializers.IntegerField()
    failed = serializers.IntegerField()
    pending = serializers.IntegerField()
    success_rate = serializers.FloatField()