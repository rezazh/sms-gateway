from django.contrib import admin
from .models import CreditAccount, CreditTransaction


@admin.register(CreditAccount)
class CreditAccountAdmin(admin.ModelAdmin):
    list_display = ['user', 'balance', 'total_charged', 'total_spent', 'updated_at']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at', 'total_charged', 'total_spent']
    list_filter = ['created_at']


@admin.register(CreditTransaction)
class CreditTransactionAdmin(admin.ModelAdmin):
    list_display = ['account', 'transaction_type', 'amount', 'balance_after', 'created_at']
    search_fields = ['account__user__username', 'reference_id']
    list_filter = ['transaction_type', 'created_at']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'