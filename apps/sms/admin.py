from django.contrib import admin
from .models import SMSMessage


@admin.register(SMSMessage)
class SMSMessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'recipient', 'status', 'priority', 'cost', 'created_at']
    search_fields = ['recipient', 'user__username', 'message']
    list_filter = ['status', 'priority', 'created_at']
    readonly_fields = ['id', 'created_at', 'updated_at', 'sent_at']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'user', 'recipient', 'message')
        }),
        ('Status and Priority', {
            'fields': ('status', 'priority', 'cost')
        }),
        ('Timing', {
            'fields': ('scheduled_at', 'sent_at', 'created_at', 'updated_at')
        }),
        ('Error and Retry', {
            'fields': ('failed_reason', 'retry_count')
        }),
    )