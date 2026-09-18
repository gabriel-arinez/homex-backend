from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.catalogo.models import Producto, ValorCatalogo
from apps.pedidos.models import Pedido


class MovimientoStock(models.Model):
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)
    tipo_movimiento = models.ForeignKey(ValorCatalogo, on_delete=models.PROTECT)
    cantidad = models.IntegerField()
    pedido = models.ForeignKey(Pedido, null=True, blank=True, on_delete=models.PROTECT)
    referencia = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)
    observaciones = models.TextField(blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "movimientos_stock"
        constraints = [
            models.CheckConstraint(
                condition=~Q(cantidad=0), name="ck_movimiento_stock_cantidad_no_cero"
            ),
            models.UniqueConstraint(
                fields=("referencia",),
                condition=Q(referencia__isnull=False),
                name="uq_reversa_por_venta",
            ),
        ]
