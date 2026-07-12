from django.urls import path
from . import views

app_name = 'creditos_compras'

urlpatterns = [
    path('compras/', views.CompraListView.as_view(), name='compra_list'),
    path('compras/create/', views.CompraCreateView.as_view(), name='compra_create'),
    path('compras/<int:pk>/detalle/', views.CompraDetailView.as_view(), name='compra_detail'),
    path('compras/<int:pk>/edit/', views.CompraUpdateView.as_view(), name='compra_update'),
    path('compras/<int:pk>/delete/', views.CompraDeleteView.as_view(), name='compra_delete'),
    path('compras/<int:pk>/cuotas/', views.CuotaCompraListView.as_view(), name='cuota_list'),
    path('compras/<int:pk>/generar-cuotas/', views.GenerarCuotasCompraView.as_view(), name='generar_cuotas'),
    path('compras/<int:pk>/pagar-multiple/', views.PagarMultipleCuotasCompraView.as_view(), name='pagar_multiple'),
    path('compras/<int:pk>/recibo-multiple/', views.ReciboMultiplePagosCompraView.as_view(), name='recibo_multiple'),
    path('cuotas/<int:pk>/pagar/', views.RegistrarPagoCompraView.as_view(), name='registrar_pago'),
    path('cuotas/<int:pk>/historial/', views.HistorialPagosCompraView.as_view(), name='historial_pagos'),
    path('cuotas/pendientes/', views.CuotasCompraPendientesView.as_view(), name='cuotas_pendientes'),
    path('pagos/<int:pk>/recibo/', views.ReciboPagoCompraView.as_view(), name='recibo_pago'),
]
