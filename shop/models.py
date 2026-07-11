from django.conf import settings
from django.db import models


class ShopOrder(models.Model):
    # Datos del cliente
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    address = models.TextField()
    dni = models.CharField(max_length=20)

    # Datos de la factura
    order_number = models.CharField(max_length=20, unique=True)  # SHP-XXXXXXXX
    status = models.CharField(max_length=20, default='pending')  # pending, paid
    created_at = models.DateTimeField(auto_now_add=True)

    # Método de pago
    payment_method = models.CharField(max_length=20)  # card, paypal, transfer
    card_last4 = models.CharField(max_length=4, blank=True, null=True)
    payment_reference = models.CharField(max_length=100, blank=True, null=True)
    payment_status = models.CharField(max_length=20, default='pending')

    # Totales
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    subtotal_iva = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    iva_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return self.order_number


class ShopOrderDetail(models.Model):
    order = models.ForeignKey(ShopOrder, on_delete=models.CASCADE, related_name='details')
    product = models.ForeignKey('billing.Product', on_delete=models.PROTECT)
    quantity = models.IntegerField(default=1)
    original_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f'{self.order.order_number} - {self.product.name}'
