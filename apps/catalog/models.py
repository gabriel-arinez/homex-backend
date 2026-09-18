from django.conf import settings
from django.db import models
from django.db.models import Q


class AuditedModel(models.Model):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="%(class)s_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="%(class)s_updated",
    )

    class Meta:
        abstract = True


class CatalogConcept(AuditedModel):
    code = models.CharField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "catalogo_conceptos"
        verbose_name = "concepto de catálogo"


class CatalogValue(AuditedModel):
    concept = models.ForeignKey(CatalogConcept, on_delete=models.PROTECT, related_name="values")
    code = models.CharField(max_length=80)
    name = models.CharField(max_length=150)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "catalogo_valores"
        constraints = [
            models.UniqueConstraint(fields=("concept", "code"), name="uq_catalogo_valor_codigo")
        ]
        indexes = [
            models.Index(fields=("concept",), name="ix_catalogo_valores_concepto"),
            models.Index(fields=("active",), name="ix_catalogo_valores_activo"),
        ]


class Product(AuditedModel):
    category = models.ForeignKey(
        CatalogValue, on_delete=models.PROTECT, related_name="products_by_category"
    )
    sku = models.CharField(max_length=80, unique=True, null=True, blank=True)
    name = models.CharField(max_length=200)
    list_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    stock = models.IntegerField(default=0)
    stock_unit = models.ForeignKey(
        CatalogValue, on_delete=models.PROTECT, related_name="products_by_stock_unit"
    )
    active = models.BooleanField(default=True)
    observations = models.TextField(blank=True)

    class Meta:
        db_table = "productos"
        constraints = [
            models.CheckConstraint(
                condition=Q(list_price__gte=0), name="ck_productos_precio_lista_nonnegative"
            ),
            models.CheckConstraint(
                condition=Q(stock__gte=0), name="ck_productos_stock_nonnegative"
            ),
        ]
        indexes = [
            models.Index(fields=("category",), name="ix_productos_categoria"),
            models.Index(fields=("stock_unit",), name="ix_productos_unidad_stock"),
            models.Index(fields=("active",), name="ix_productos_activo"),
            models.Index(fields=("name",), name="ix_productos_nombre"),
        ]


class ChairProduct(AuditedModel):
    product = models.OneToOneField(
        Product,
        primary_key=True,
        on_delete=models.CASCADE,
        db_column="producto_id",
        related_name="chair",
    )
    brand = models.ForeignKey(
        CatalogValue, null=True, blank=True, on_delete=models.PROTECT, related_name="chair_brands"
    )
    model = models.CharField(max_length=150, blank=True)
    primary_color = models.ForeignKey(
        CatalogValue,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="chairs_primary_color",
    )
    secondary_color = models.ForeignKey(
        CatalogValue,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="chairs_secondary_color",
    )
    specifications = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "productos_silla"
        constraints = [
            models.CheckConstraint(
                condition=Q(secondary_color__isnull=True) | Q(primary_color__isnull=False),
                name="ck_silla_color_secundario_requiere_primario",
            ),
            models.CheckConstraint(
                condition=Q(primary_color__isnull=True)
                | Q(secondary_color__isnull=True)
                | ~Q(primary_color=models.F("secondary_color")),
                name="ck_silla_colores_distintos",
            ),
        ]


class FloorProduct(AuditedModel):
    product = models.OneToOneField(
        Product,
        primary_key=True,
        on_delete=models.CASCADE,
        db_column="producto_id",
        related_name="floor",
    )
    brand = models.ForeignKey(
        CatalogValue, null=True, blank=True, on_delete=models.PROTECT, related_name="floor_brands"
    )
    model = models.CharField(max_length=150, blank=True)
    type = models.ForeignKey(
        CatalogValue, null=True, blank=True, on_delete=models.PROTECT, related_name="floor_types"
    )
    material = models.ForeignKey(
        CatalogValue,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="floor_materials",
    )
    design = models.ForeignKey(
        CatalogValue, null=True, blank=True, on_delete=models.PROTECT, related_name="floor_designs"
    )
    thickness_mm = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    finish = models.ForeignKey(
        CatalogValue, null=True, blank=True, on_delete=models.PROTECT, related_name="floor_finishes"
    )
    length_mm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    width_mm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    m2_per_box = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)

    class Meta:
        db_table = "productos_piso"
        constraints = [
            models.CheckConstraint(
                condition=Q(thickness_mm__isnull=True) | Q(thickness_mm__gt=0),
                name="ck_piso_espesor_positive",
            ),
            models.CheckConstraint(
                condition=Q(length_mm__isnull=True) | Q(length_mm__gt=0),
                name="ck_piso_largo_positive",
            ),
            models.CheckConstraint(
                condition=Q(width_mm__isnull=True) | Q(width_mm__gt=0),
                name="ck_piso_ancho_positive",
            ),
            models.CheckConstraint(
                condition=Q(m2_per_box__isnull=True) | Q(m2_per_box__gt=0),
                name="ck_piso_m2_caja_positive",
            ),
        ]


class ProductDiscount(AuditedModel):
    product = models.OneToOneField(Product, on_delete=models.PROTECT, related_name="discount")
    price_before = models.DecimalField(max_digits=12, decimal_places=2)
    price_now = models.DecimalField(max_digits=12, decimal_places=2)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "productos_descuento"
        constraints = [
            models.CheckConstraint(
                condition=Q(price_before__gte=0) & Q(price_now__gte=0),
                name="ck_descuento_precios_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(price_now__lt=models.F("price_before")),
                name="ck_descuento_precio_reducido",
            ),
            models.CheckConstraint(
                condition=Q(end_date__isnull=True)
                | Q(start_date__isnull=True)
                | Q(end_date__gte=models.F("start_date")),
                name="ck_descuento_fechas",
            ),
        ]
