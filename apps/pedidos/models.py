from django.conf import settings
from django.db import models


class Pedido(models.Model):
    proforma = models.OneToOneField("proformas.Proforma", on_delete=models.PROTECT)
    fecha_confirmacion = models.DateTimeField()
    estado = models.ForeignKey("catalogo.ValorCatalogo", on_delete=models.PROTECT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "pedidos"


class TransicionEstadoPedido(models.Model):
    estado_origen = models.ForeignKey(
        "catalogo.ValorCatalogo", on_delete=models.PROTECT, related_name="+"
    )
    estado_destino = models.ForeignKey(
        "catalogo.ValorCatalogo", on_delete=models.PROTECT, related_name="+"
    )

    pk = models.CompositePrimaryKey("estado_origen", "estado_destino")

    class Meta:
        db_table = "transiciones_estado_pedido"
