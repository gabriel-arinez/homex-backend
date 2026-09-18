from django.conf import settings
from django.db import models

from apps.catalogo.models import ValorCatalogo
from apps.proformas.models import Proforma


class Pedido(models.Model):
    proforma = models.OneToOneField(
        Proforma, on_delete=models.PROTECT, db_column="proforma_id", related_name="pedido"
    )
    fecha_confirmacion = models.DateTimeField(auto_now_add=True)
    estado = models.ForeignKey(ValorCatalogo, on_delete=models.PROTECT)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "pedidos"


class TransicionEstadoPedido(models.Model):
    origen = models.ForeignKey(
        ValorCatalogo, on_delete=models.PROTECT, related_name="+", db_column="estado_origen_id"
    )
    destino = models.ForeignKey(
        ValorCatalogo, on_delete=models.PROTECT, related_name="+", db_column="estado_destino_id"
    )

    class Meta:
        db_table = "transiciones_estado_pedido"
        constraints = [
            models.UniqueConstraint(fields=("origen", "destino"), name="pk_transicion_estado")
        ]
