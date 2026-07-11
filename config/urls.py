from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('security/', include('security.urls')),
    path('', include('billing.urls')),
    path('purchases/', include('purchasing.urls')),
    path('shop/', include('shop.urls')),
    path('creditos-ventas/', include('creditos_ventas.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
