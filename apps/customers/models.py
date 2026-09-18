from django.conf import settings
from django.db import models

from apps.catalog.models import CatalogValue


class Customer(models.Model):
    customer_type = models.ForeignKey(CatalogValue, on_delete=models.PROTECT)
    first_names = models.CharField(max_length=150, blank=True)
    last_names = models.CharField(max_length=150, blank=True)
    company = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    observations = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="customers_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="customers_updated",
    )

    class Meta:
        db_table = "clientes"
        indexes = [
            models.Index(fields=("customer_type",), name="ix_clientes_tipo"),
            models.Index(fields=("active",), name="ix_clientes_activo"),
            models.Index(fields=("company",), name="ix_clientes_empresa"),
        ]
