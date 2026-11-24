from django.conf import settings
from django.db import models
from django.utils import timezone


class MovimientoStock(models.Model):
    producto = models.ForeignKey("catalogo.Producto", on_delete=models.PROTECT)
    fecha = models.DateTimeField()
    registrado_en = models.DateTimeField(
        default=timezone.now, null=True, blank=True, editable=False
    )
    tipo_movimiento = models.ForeignKey("catalogo.ValorCatalogo", on_delete=models.PROTECT)
    cantidad = models.DecimalField(max_digits=14, decimal_places=4)
    pedido = models.ForeignKey("pedidos.Pedido", null=True, blank=True, on_delete=models.PROTECT)
    movimiento_referencia = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT
    )
    motivo = models.CharField(max_length=50, null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    clave_idempotencia = models.UUIDField(null=True, blank=True, unique=True, editable=False)

    class Meta:
        db_table = "movimientos_stock"
