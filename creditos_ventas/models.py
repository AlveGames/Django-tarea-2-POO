from django.db import models
from billing.models import Invoice

class CuotaVenta(models.Model):
    factura = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="cuotas")
    numero = models.PositiveIntegerField()
    fecha_vencimiento = models.DateField()
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    saldo = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(
        max_length=15,
        choices=[("PENDIENTE", "PENDIENTE"), ("PAGADA", "PAGADA")],
        default="PENDIENTE"
    )
    class Meta:
        permissions = [
            ('export_cuotaventa', 'Can export cuota venta'),
            ('print_cuotaventa', 'Can print cuota venta'),
        ]
    def __str__(self):
        return f"Cuota {self.numero} - {self.factura}"

class PagoCuotaVenta(models.Model):
    cuota = models.ForeignKey(CuotaVenta, on_delete=models.PROTECT)
    fecha = models.DateField()
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    observacion = models.TextField(blank=True)
    def __str__(self):
        return f"Pago {self.valor} - Cuota {self.cuota.numero}"
