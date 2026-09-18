from django.conf import settings
from django.db import models


class Recibo(models.Model):
    numero = models.BigIntegerField(unique=True)
    pedido = models.ForeignKey("pedidos.Pedido", on_delete=models.PROTECT)
    nombre_completo = models.CharField(max_length=250)
    monto_en_letras = models.TextField()
    concepto = models.TextField()
    tipo_pago = models.ForeignKey("catalogo.ValorCatalogo", on_delete=models.PROTECT)
    numero_cheque = models.CharField(max_length=80, null=True, blank=True)
    banco = models.CharField(max_length=150, null=True, blank=True)
    total = models.DecimalField(max_digits=14, decimal_places=2)
    pago_actual = models.DecimalField(max_digits=14, decimal_places=2)
    a_cuenta = models.DecimalField(max_digits=14, decimal_places=2)
    saldo = models.DecimalField(max_digits=14, decimal_places=2)
    estado = models.CharField(max_length=10, default="EMITIDO")
    fecha = models.DateField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "recibos"
