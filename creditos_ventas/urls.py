from django.urls import path
from . import views

app_name = 'creditos_ventas'

urlpatterns = [
    path('facturas/', views.FacturaVentaListView.as_view(), name='factura_list'),
    path('facturas/create/', views.FacturaVentaCreateView.as_view(), name='factura_create'),
    path('facturas/<int:pk>/detalle/', views.FacturaVentaDetailView.as_view(), name='factura_detail'),
    path('facturas/<int:pk>/edit/', views.FacturaVentaUpdateView.as_view(), name='factura_update'),
    path('facturas/<int:pk>/delete/', views.FacturaVentaDeleteView.as_view(), name='factura_delete'),
    path('facturas/<int:pk>/cuotas/', views.CuotaVentaListView.as_view(), name='cuota_list'),
    path('facturas/<int:pk>/generar-cuotas/', views.GenerarCuotasView.as_view(), name='generar_cuotas'),
    path('cuotas/<int:pk>/pagar/', views.RegistrarPagoView.as_view(), name='registrar_pago'),
    path('cuotas/<int:pk>/historial/', views.HistorialPagosView.as_view(), name='historial_pagos'),
    path('cuotas/pendientes/', views.CuotasPendientesView.as_view(), name='cuotas_pendientes'),
]
