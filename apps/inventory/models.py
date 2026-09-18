from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.catalog.models import CatalogValue, Product
from apps.orders.models import Order


class StockMovement(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    movement_type = models.ForeignKey(CatalogValue, on_delete=models.PROTECT)
    quantity = models.IntegerField()
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.PROTECT)
    reference = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "movimientos_stock"
        constraints = [
            models.CheckConstraint(
                condition=~Q(quantity=0), name="ck_movimiento_stock_cantidad_no_cero"
            ),
            models.UniqueConstraint(
                fields=("reference",),
                condition=Q(reference__isnull=False),
                name="uq_reversa_por_venta",
            ),
        ]
