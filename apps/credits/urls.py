from django.urls import path
from .views import (
    CreditBalanceView,
    ChargeAccountView,
    CreditTransactionsView
)

app_name = 'credits'

urlpatterns = [
    path('balance/', CreditBalanceView.as_view(), name='balance'),
    path('charge/', ChargeAccountView.as_view(), name='charge'),
    path('transactions/', CreditTransactionsView.as_view(), name='transactions'),
]