from django.conf import settings
from django.db import models


class Pedido(models.Model):
    proforma = models.OneToOneField("proformas.Proforma", on_delete=models.PROTECT)
    fecha_confirmacion = models.DateTimeField()
    fecha_entrega_efectiva = models.DateField(null=True, blank=True)
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


class HistorialEstadoPedido(models.Model):
    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        related_name="historial_estados",
    )
    estado_anterior = models.ForeignKey(
        "catalogo.ValorCatalogo",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    estado_nuevo = models.ForeignKey(
        "catalogo.ValorCatalogo",
        on_delete=models.PROTECT,
        related_name="+",
    )
    cambiado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    es_automatico = models.BooleanField(default=False)
    origen = models.CharField(max_length=32, default="MANUAL")
    fecha = models.DateTimeField()
    observaciones = models.TextField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "pedidos_historial_estados"
        ordering = ["fecha", "id"]
