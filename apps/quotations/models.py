from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.timezone import localdate

from apps.catalog.models import CatalogValue, Product
from apps.customers.models import Customer


class Quotation(models.Model):
    number = models.BigIntegerField(unique=True, null=True, editable=False)
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.PROTECT)
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="quotations_sold"
    )
    status = models.ForeignKey(
        CatalogValue, on_delete=models.PROTECT, related_name="quotations_by_status"
    )
    title = models.CharField(max_length=250, blank=True)
    date = models.DateField(default=localdate)
    delivery_term = models.CharField(max_length=100, blank=True)
    offer_validity = models.SmallIntegerField(null=True, blank=True)
    advance_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    currency = models.ForeignKey(
        CatalogValue, on_delete=models.PROTECT, related_name="quotations_by_currency"
    )
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    observations = models.TextField(blank=True)
    prospect_name = models.CharField(max_length=250, blank=True)
    prospect_company = models.CharField(max_length=200, blank=True)
    prospect_phone = models.CharField(max_length=40, blank=True)
    prospect_address = models.TextField(blank=True)
    customer_name_snapshot = models.CharField(max_length=300, blank=True)
    customer_company_snapshot = models.CharField(max_length=200, blank=True)
    customer_phone_snapshot = models.CharField(max_length=40, blank=True)
    customer_address_snapshot = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="quotations_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="quotations_updated",
    )

    class Meta:
        db_table = "proformas"
        constraints = [
            models.CheckConstraint(
                condition=Q(offer_validity__isnull=True) | Q(offer_validity__gte=0),
                name="ck_proforma_validez_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(advance_percentage__isnull=True)
                | (Q(advance_percentage__gte=0) & Q(advance_percentage__lte=100)),
                name="ck_proforma_adelanto",
            ),
            models.CheckConstraint(
                condition=Q(subtotal__gte=0) & Q(discount_total__gte=0) & Q(total__gte=0),
                name="ck_proforma_importes",
            ),
        ]


class QuotationLine(models.Model):
    class CalculationMode(models.TextChoices):
        UNIT = "PRECIO_UNITARIO"
        NEGOTIATED = "TOTAL_NEGOCIADO"

    quotation = models.ForeignKey(Quotation, on_delete=models.PROTECT, related_name="lines")
    item_type = models.ForeignKey(
        CatalogValue, on_delete=models.PROTECT, related_name="quotation_lines_by_type"
    )
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.PROTECT)
    name = models.CharField(max_length=250)
    description = models.TextField(blank=True)
    quantity = models.IntegerField()
    unit = models.ForeignKey(
        CatalogValue, on_delete=models.PROTECT, related_name="quotation_lines_by_unit"
    )
    calculation_mode = models.CharField(
        max_length=20, choices=CalculationMode.choices, default=CalculationMode.UNIT
    )
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    negotiated_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        db_table = "proformas_detalle"
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="ck_detalle_cantidad_positive"
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0), name="ck_detalle_precio_nonnegative"
            ),
        ]


class FurnitureSpecification(models.Model):
    line = models.OneToOneField(
        QuotationLine,
        on_delete=models.CASCADE,
        related_name="furniture_specification",
        db_column="proforma_detalle_id",
    )
    furniture_type = models.ForeignKey(
        CatalogValue, null=True, blank=True, on_delete=models.PROTECT
    )
    schema_version = models.SmallIntegerField(default=1)
    thickness = models.JSONField(null=True, blank=True)
    primary_color = models.CharField(max_length=150, blank=True)
    secondary_color = models.CharField(max_length=150, blank=True)
    dimensions = models.JSONField(null=True, blank=True)
    accessories = models.JSONField(null=True, blank=True)
    observations = models.TextField(blank=True)

    class Meta:
        db_table = "especificaciones_mueble"
        constraints = [
            models.CheckConstraint(
                condition=Q(schema_version=1), name="ck_especificacion_schema_version"
            )
        ]
