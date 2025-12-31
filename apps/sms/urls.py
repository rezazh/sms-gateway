from django.urls import path
from .views import (
    SendSMSView,
    SMSListView,
    SMSDetailView,
    CancelSMSView,
    SMSStatisticsView
)

app_name = 'sms'

urlpatterns = [
    path('send/', SendSMSView.as_view(), name='send'),
    path('messages/', SMSListView.as_view(), name='list'),
    path('messages/<uuid:message_id>/', SMSDetailView.as_view(), name='detail'),
    path('messages/<uuid:message_id>/cancel/', CancelSMSView.as_view(), name='cancel'),
    path('statistics/', SMSStatisticsView.as_view(), name='statistics'),
]