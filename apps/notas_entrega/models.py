from django.conf import settings
from django.db import models


class NotaEntrega(models.Model):
    pedido = models.OneToOneField("pedidos.Pedido", on_delete=models.PROTECT)
    vendedor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    numero = models.BigIntegerField(unique=True)
    fecha = models.DateField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "notas_entrega"
