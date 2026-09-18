from django.conf import settings
from django.db import models
from django.utils.timezone import localdate

from apps.orders.models import Order


class DeliveryNote(models.Model):
    order = models.OneToOneField(Order, on_delete=models.PROTECT, db_column="pedido_id")
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="delivery_notes"
    )
    number = models.BigIntegerField(unique=True, editable=False)
    date = models.DateField(default=localdate)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "notas_entrega"
        indexes = [
            models.Index(fields=("seller",), name="ix_notas_entrega_vendedor"),
            models.Index(fields=("date",), name="ix_notas_entrega_fecha"),
        ]
