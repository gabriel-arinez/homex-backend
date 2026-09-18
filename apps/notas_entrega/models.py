from django.conf import settings
from django.db import models
from django.utils.timezone import localdate

from apps.pedidos.models import Pedido


class NotaEntrega(models.Model):
    pedido = models.OneToOneField(Pedido, on_delete=models.PROTECT, db_column="pedido_id")
    vendedor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="nota_entregas"
    )
    numero = models.BigIntegerField(unique=True, editable=False)
    fecha = models.DateField(default=localdate)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "notas_entrega"
        indexes = [
            models.Index(fields=("vendedor",), name="ix_notas_entrega_vendedor"),
            models.Index(fields=("fecha",), name="ix_notas_entrega_fecha"),
        ]
