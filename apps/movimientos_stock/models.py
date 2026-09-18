from django.conf import settings
from django.db import models


class MovimientoStock(models.Model):
    producto = models.ForeignKey("catalogo.Producto", on_delete=models.PROTECT)
    fecha = models.DateTimeField()
    tipo_movimiento = models.ForeignKey("catalogo.ValorCatalogo", on_delete=models.PROTECT)
    cantidad = models.IntegerField()
    pedido = models.ForeignKey("pedidos.Pedido", null=True, blank=True, on_delete=models.PROTECT)
    movimiento_referencia = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT
    )
    observaciones = models.TextField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "movimientos_stock"
