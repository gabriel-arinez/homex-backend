from django.conf import settings
from django.db import models

from apps.catalogo.models import ValorCatalogo
from apps.pedidos.models import Pedido


class OrdenTrabajo(models.Model):
    pedido = models.OneToOneField(
        Pedido, on_delete=models.PROTECT, db_column="pedido_id", related_name="orden_trabajo"
    )
    jefe_taller = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    numero = models.BigIntegerField(unique=True, null=True)
    fecha = models.DateField(auto_now_add=True)
    estado = models.ForeignKey(ValorCatalogo, on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "ordenes_trabajo"
