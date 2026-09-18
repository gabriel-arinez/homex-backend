from django.conf import settings
from django.db import models

from apps.catalog.models import CatalogValue
from apps.quotations.models import Quotation


class Order(models.Model):
    quotation = models.OneToOneField(
        Quotation, on_delete=models.PROTECT, db_column="proforma_id", related_name="order"
    )
    confirmed_at = models.DateTimeField(auto_now_add=True)
    status = models.ForeignKey(CatalogValue, on_delete=models.PROTECT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "pedidos"


class OrderTransition(models.Model):
    source = models.ForeignKey(
        CatalogValue, on_delete=models.PROTECT, related_name="+", db_column="estado_origen_id"
    )
    target = models.ForeignKey(
        CatalogValue, on_delete=models.PROTECT, related_name="+", db_column="estado_destino_id"
    )

    class Meta:
        db_table = "transiciones_estado_pedido"
        constraints = [
            models.UniqueConstraint(fields=("source", "target"), name="pk_transicion_estado")
        ]
