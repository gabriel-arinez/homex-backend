from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.timezone import localdate

from apps.catalog.models import CatalogValue
from apps.orders.models import Order


class Receipt(models.Model):
    class Status(models.TextChoices):
        ISSUED = "EMITIDO", "Emitido"
        VOIDED = "ANULADO", "Anulado"

    number = models.BigIntegerField(unique=True, editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="receipts")
    full_name = models.CharField(max_length=250)
    amount_in_words = models.TextField()
    concept = models.TextField()
    payment_type = models.ForeignKey(CatalogValue, on_delete=models.PROTECT)
    check_number = models.CharField(max_length=80, blank=True)
    bank = models.CharField(max_length=150, blank=True)
    total = models.DecimalField(max_digits=14, decimal_places=2)
    current_payment = models.DecimalField(max_digits=14, decimal_places=2)
    on_account = models.DecimalField(max_digits=14, decimal_places=2)
    balance = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ISSUED)
    date = models.DateField(default=localdate)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "recibos"
        constraints = [
            models.CheckConstraint(condition=Q(total__gt=0), name="ck_recibo_total_positive"),
            models.CheckConstraint(
                condition=Q(current_payment__gt=0), name="ck_recibo_pago_actual_positive"
            ),
            models.CheckConstraint(
                condition=Q(on_account__gte=0), name="ck_recibo_a_cuenta_nonnegative"
            ),
            models.CheckConstraint(condition=Q(balance__gte=0), name="ck_recibo_saldo_nonnegative"),
        ]
        indexes = [
            models.Index(fields=("order",), name="ix_recibos_pedido"),
            models.Index(fields=("date",), name="ix_recibos_fecha"),
            models.Index(fields=("payment_type",), name="ix_recibos_tipo_pago"),
        ]
