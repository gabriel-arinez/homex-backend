from django.conf import settings
from django.db import models

from apps.catalog.models import CatalogValue
from apps.orders.models import Order


class WorkOrder(models.Model):
    order = models.OneToOneField(Order, on_delete=models.PROTECT, db_column="pedido_id")
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    number = models.BigIntegerField(unique=True, null=True)
    date = models.DateField(auto_now_add=True)
    status = models.ForeignKey(CatalogValue, on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "ordenes_trabajo"
