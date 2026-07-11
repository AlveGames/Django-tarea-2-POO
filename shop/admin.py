from django.contrib import admin

from .models import ShopOrder, ShopOrderDetail


@admin.register(ShopOrder)
class ShopOrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'full_name', 'status', 'payment_status', 'total', 'created_at')
    search_fields = ('order_number', 'full_name', 'email', 'dni')
    list_filter = ('status', 'payment_status', 'payment_method')


@admin.register(ShopOrderDetail)
class ShopOrderDetailAdmin(admin.ModelAdmin):
    list_display = ('order', 'product', 'quantity', 'unit_price', 'subtotal')
    search_fields = ('order__order_number', 'product__name')
