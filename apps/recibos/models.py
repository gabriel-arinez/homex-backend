from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.timezone import localdate

from apps.catalogo.models import ValorCatalogo
from apps.pedidos.models import Pedido


class Recibo(models.Model):
    class Status(models.TextChoices):
        ISSUED = "EMITIDO", "Emitido"
        VOIDED = "ANULADO", "Anulado"

    numero = models.BigIntegerField(unique=True, editable=False)
    pedido = models.ForeignKey(Pedido, on_delete=models.PROTECT, related_name="recibos")
    nombre_completo = models.CharField(max_length=250)
    monto_literal = models.TextField()
    concepto = models.TextField()
    tipo_pago = models.ForeignKey(ValorCatalogo, on_delete=models.PROTECT)
    numero_cheque = models.CharField(max_length=80, blank=True)
    banco = models.CharField(max_length=150, blank=True)
    total = models.DecimalField(max_digits=14, decimal_places=2)
    pago_actual = models.DecimalField(max_digits=14, decimal_places=2)
    a_cuenta = models.DecimalField(max_digits=14, decimal_places=2)
    saldo = models.DecimalField(max_digits=14, decimal_places=2)
    estado = models.CharField(max_length=10, choices=Status.choices, default=Status.ISSUED)
    fecha = models.DateField(default=localdate)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "recibos"
        constraints = [
            models.CheckConstraint(condition=Q(total__gt=0), name="ck_recibo_total_positive"),
            models.CheckConstraint(
                condition=Q(pago_actual__gt=0), name="ck_recibo_pago_actual_positive"
            ),
            models.CheckConstraint(
                condition=Q(a_cuenta__gte=0), name="ck_recibo_a_cuenta_nonnegative"
            ),
            models.CheckConstraint(condition=Q(saldo__gte=0), name="ck_recibo_saldo_nonnegative"),
        ]
        indexes = [
            models.Index(fields=("pedido",), name="ix_recibos_pedido"),
            models.Index(fields=("fecha",), name="ix_recibos_fecha"),
            models.Index(fields=("tipo_pago",), name="ix_recibos_tipo_pago"),
        ]
