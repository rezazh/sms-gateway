from django.contrib import admin
from django.urls import path, include
from apps.accounts.views import HealthCheckView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),

    path('health/', HealthCheckView.as_view(), name='health-check'),

    path('api/credits/', include('apps.credits.urls')),
    path('api/sms/', include('apps.sms.urls')),

    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('', include('django_prometheus.urls')),

]