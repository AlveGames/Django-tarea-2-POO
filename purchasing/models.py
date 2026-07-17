from django.db import models
from decimal import Decimal
from billing.models import Supplier, Product

class Purchase(models.Model):
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name='purchases'
    )
    document_number = models.CharField(
        max_length=20, verbose_name='Supplier Invoice No.'
    )
    purchase_date = models.DateTimeField(auto_now_add=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    tipo_pago = models.CharField(
        max_length=10,
        choices=[("CONTADO", "CONTADO"), ("CREDITO", "CREDITO")],
        default="CONTADO"
    )
    saldo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estado = models.CharField(
        max_length=15,
        choices=[("PENDIENTE", "PENDIENTE"), ("PAGADA", "PAGADA")],
        default="PENDIENTE"
    )

    class Meta:
        verbose_name = 'Purchase'
        verbose_name_plural = 'Purchases'
        ordering = ['-purchase_date']
        permissions = [
            ('export_purchase', 'Can export purchase'),
            ('print_purchase', 'Can print purchase'),
        ]

    def __str__(self):
        return f'Purchase #{self.id} - {self.supplier}'

class PurchaseDetail(models.Model):
    purchase = models.ForeignKey(
        Purchase, on_delete=models.CASCADE, related_name='details'
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='purchase_details'
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f'{self.product.name} x {self.quantity}'

    def save(self, *args, **kwargs):
        self.subtotal = self.quantity * self.unit_cost
        super().save(*args, **kwargs)