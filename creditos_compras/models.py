from django.db import models
from purchasing.models import Purchase

class CuotaCompra(models.Model):
    compra = models.ForeignKey(Purchase, on_delete=models.PROTECT, related_name="cuotas")
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
            ('export_cuotacompra', 'Can export cuota compra'),
            ('print_cuotacompra', 'Can print cuota compra'),
        ]
    def __str__(self):
        return f"Cuota {self.numero} - {self.compra}"

class PagoCuotaCompra(models.Model):
    cuota = models.ForeignKey(CuotaCompra, on_delete=models.PROTECT)
    fecha = models.DateField()
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    observacion = models.TextField(blank=True)
    def __str__(self):
        return f"Pago {self.valor} - Cuota {self.cuota.numero}"
