from django.conf import settings
from django.db import models
from django.db.models import Q


class AuditedModel(models.Model):
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="%(class)s_created",
    )
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="%(class)s_updated",
    )

    class Meta:
        abstract = True


class ConceptoCatalogo(AuditedModel):
    codigo = models.CharField(max_length=80, unique=True)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "catalogo_conceptos"
        verbose_name = "concepto de catálogo"


class ValorCatalogo(AuditedModel):
    concepto = models.ForeignKey(ConceptoCatalogo, on_delete=models.PROTECT, related_name="valores")
    codigo = models.CharField(max_length=80)
    nombre = models.CharField(max_length=150)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "catalogo_valores"
        constraints = [
            models.UniqueConstraint(fields=("concepto", "codigo"), name="uq_catalogo_valor_codigo")
        ]
        indexes = [
            models.Index(fields=("concepto",), name="ix_catalogo_valores_concepto"),
            models.Index(fields=("activo",), name="ix_catalogo_valores_activo"),
        ]


class Producto(AuditedModel):
    categoria = models.ForeignKey(
        ValorCatalogo, on_delete=models.PROTECT, related_name="products_by_categoria"
    )
    sku = models.CharField(max_length=80, unique=True, null=True, blank=True)
    nombre = models.CharField(max_length=200)
    precio_lista = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    stock = models.IntegerField(default=0)
    unidad_stock = models.ForeignKey(
        ValorCatalogo, on_delete=models.PROTECT, related_name="products_by_unidad_stock"
    )
    activo = models.BooleanField(default=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        db_table = "productos"
        constraints = [
            models.CheckConstraint(
                condition=Q(precio_lista__gte=0), name="ck_productos_precio_lista_nonnegative"
            ),
            models.CheckConstraint(
                condition=Q(stock__gte=0), name="ck_productos_stock_nonnegative"
            ),
        ]
        indexes = [
            models.Index(fields=("categoria",), name="ix_productos_categoria"),
            models.Index(fields=("unidad_stock",), name="ix_productos_unidad_stock"),
            models.Index(fields=("activo",), name="ix_productos_activo"),
            models.Index(fields=("nombre",), name="ix_productos_nombre"),
        ]


class ProductoSilla(AuditedModel):
    producto = models.OneToOneField(
        Producto,
        primary_key=True,
        on_delete=models.CASCADE,
        db_column="producto_id",
        related_name="silla",
    )
    marca = models.ForeignKey(
        ValorCatalogo, null=True, blank=True, on_delete=models.PROTECT, related_name="sillas_por_marca"
    )
    modelo = models.CharField(max_length=150, blank=True)
    color_primario = models.ForeignKey(
        ValorCatalogo,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="sillas_color_primario",
    )
    color_secundario = models.ForeignKey(
        ValorCatalogo,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="sillas_color_secundario",
    )
    especificaciones = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "productos_silla"
        constraints = [
            models.CheckConstraint(
                condition=Q(color_secundario__isnull=True) | Q(color_primario__isnull=False),
                name="ck_silla_color_secundario_requiere_primario",
            ),
            models.CheckConstraint(
                condition=Q(color_primario__isnull=True)
                | Q(color_secundario__isnull=True)
                | ~Q(color_primario=models.F("color_secundario")),
                name="ck_silla_colores_distintos",
            ),
        ]


class ProductoPiso(AuditedModel):
    producto = models.OneToOneField(
        Producto,
        primary_key=True,
        on_delete=models.CASCADE,
        db_column="producto_id",
        related_name="piso",
    )
    marca = models.ForeignKey(
        ValorCatalogo, null=True, blank=True, on_delete=models.PROTECT, related_name="pisos_por_marca"
    )
    modelo = models.CharField(max_length=150, blank=True)
    tipo = models.ForeignKey(
        ValorCatalogo, null=True, blank=True, on_delete=models.PROTECT, related_name="pisos_por_tipo"
    )
    material = models.ForeignKey(
        ValorCatalogo,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pisos_por_material",
    )
    diseno = models.ForeignKey(
        ValorCatalogo, null=True, blank=True, on_delete=models.PROTECT, related_name="pisos_por_diseno"
    )
    espesor_mm = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    acabado = models.ForeignKey(
        ValorCatalogo,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pisos_por_acabado",
    )
    largo_mm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    ancho_mm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    m2_por_caja = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)

    class Meta:
        db_table = "productos_piso"
        constraints = [
            models.CheckConstraint(
                condition=Q(espesor_mm__isnull=True) | Q(espesor_mm__gt=0),
                name="ck_piso_espesor_positive",
            ),
            models.CheckConstraint(
                condition=Q(largo_mm__isnull=True) | Q(largo_mm__gt=0),
                name="ck_piso_largo_positive",
            ),
            models.CheckConstraint(
                condition=Q(ancho_mm__isnull=True) | Q(ancho_mm__gt=0),
                name="ck_piso_ancho_positive",
            ),
            models.CheckConstraint(
                condition=Q(m2_por_caja__isnull=True) | Q(m2_por_caja__gt=0),
                name="ck_piso_m2_caja_positive",
            ),
        ]


class DescuentoProducto(AuditedModel):
    producto = models.OneToOneField(Producto, on_delete=models.PROTECT, related_name="descuento")
    precio_antes = models.DecimalField(max_digits=12, decimal_places=2)
    precio_ahora = models.DecimalField(max_digits=12, decimal_places=2)
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_fin = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "productos_descuento"
        constraints = [
            models.CheckConstraint(
                condition=Q(precio_antes__gte=0) & Q(precio_ahora__gte=0),
                name="ck_descuento_precios_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(precio_ahora__lt=models.F("precio_antes")),
                name="ck_descuento_precio_reducido",
            ),
            models.CheckConstraint(
                condition=Q(fecha_fin__isnull=True)
                | Q(fecha_inicio__isnull=True)
                | Q(fecha_fin__gte=models.F("fecha_inicio")),
                name="ck_descuento_fechas",
            ),
        ]
