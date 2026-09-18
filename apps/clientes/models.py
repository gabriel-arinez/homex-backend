from django.conf import settings
from django.db import models

from apps.catalogo.models import ValorCatalogo


class Cliente(models.Model):
    tipo_cliente = models.ForeignKey(ValorCatalogo, on_delete=models.PROTECT)
    nombres = models.CharField(max_length=150, blank=True)
    apellidos = models.CharField(max_length=150, blank=True)
    empresa = models.CharField(max_length=200, blank=True)
    celular = models.CharField(max_length=40, blank=True)
    direccion = models.TextField(blank=True)
    observaciones = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="customers_created",
    )
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="customers_updated",
    )

    class Meta:
        db_table = "clientes"
        indexes = [
            models.Index(fields=("tipo_cliente",), name="ix_clientes_tipo"),
            models.Index(fields=("activo",), name="ix_clientes_activo"),
            models.Index(fields=("empresa",), name="ix_clientes_empresa"),
        ]
