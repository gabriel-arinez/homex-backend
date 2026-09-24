from django.conf import settings
from django.db import models


class OrdenTrabajo(models.Model):
    pedido = models.OneToOneField("pedidos.Pedido", on_delete=models.PROTECT)
    jefe_taller = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    numero = models.BigIntegerField(unique=True)
    fecha = models.DateField()
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_fin = models.DateField(null=True, blank=True)
    responsable_recepcion = models.CharField(max_length=200, null=True, blank=True)
    fecha_entrega = models.DateField(null=True, blank=True)
    lugar_entrega = models.TextField(null=True, blank=True)
    estado_saldo = models.ForeignKey(
        "catalogo.ValorCatalogo", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    estado = models.ForeignKey("catalogo.ValorCatalogo", on_delete=models.PROTECT, related_name="+")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "ordenes_trabajo"
