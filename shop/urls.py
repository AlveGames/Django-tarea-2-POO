from django.urls import path

from . import views

app_name = 'shop'

urlpatterns = [
    path('', views.CatalogView.as_view(), name='catalog'),
    path('cart/', views.CartView.as_view(), name='cart'),
    path('cart/add/<int:pk>/', views.add_to_cart, name='add_to_cart'),
    path('cart/remove/<int:pk>/', views.remove_from_cart, name='remove_from_cart'),
    path('cart/update/<int:pk>/', views.update_cart, name='update_cart'),
    path('checkout/', views.CheckoutView.as_view(), name='checkout'),
    path('checkout/process/', views.process_payment, name='process_payment'),
    path('orders/', views.MisOrdenesView.as_view(), name='mis_ordenes'),
    path('orders/<int:pk>/receipt/', views.OrderReceiptView.as_view(), name='receipt'),
]
