from django.conf import settings
from django.db import models


class Auditoria(models.Model):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        abstract = True


class ConceptoCatalogo(Auditoria):
    codigo = models.CharField(max_length=80, unique=True)
    descripcion = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "catalogo_conceptos"


class ValorCatalogo(Auditoria):
    concepto = models.ForeignKey(ConceptoCatalogo, on_delete=models.PROTECT)
    codigo = models.CharField(max_length=80)
    nombre = models.CharField(max_length=150)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "catalogo_valores"
        constraints = [
            models.UniqueConstraint(fields=["concepto", "codigo"], name="uq_catalogo_valor_codigo")
        ]


class Producto(Auditoria):
    categoria = models.ForeignKey(ValorCatalogo, on_delete=models.PROTECT, related_name="+")
    sku = models.CharField(max_length=80, unique=True, null=True, blank=True)
    nombre = models.CharField(max_length=200)
    precio_lista = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    stock = models.IntegerField(default=0)
    unidad_stock = models.ForeignKey(ValorCatalogo, on_delete=models.PROTECT, related_name="+")
    activo = models.BooleanField(default=True)
    observaciones = models.TextField(null=True, blank=True)
    imagen_principal = models.ImageField(upload_to="productos/", null=True, blank=True)
    imagen_principal_variantes = models.JSONField(default=dict, blank=True)
    imagen_principal_dimensiones = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "productos"


class ProductoSilla(Auditoria):
    producto = models.OneToOneField(Producto, primary_key=True, on_delete=models.CASCADE)
    marca = models.ForeignKey(
        ValorCatalogo, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    modelo = models.CharField(max_length=150, null=True, blank=True)
    color_primario = models.ForeignKey(
        ValorCatalogo, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    color_secundario = models.ForeignKey(
        ValorCatalogo, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    especificaciones = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "productos_silla"


class ProductoPiso(Auditoria):
    producto = models.OneToOneField(Producto, primary_key=True, on_delete=models.CASCADE)
    marca = models.ForeignKey(
        ValorCatalogo, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    modelo = models.CharField(max_length=150, null=True, blank=True)
    tipo = models.ForeignKey(
        ValorCatalogo, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    material = models.ForeignKey(
        ValorCatalogo, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    diseno = models.ForeignKey(
        ValorCatalogo, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    espesor_mm = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    acabado = models.ForeignKey(
        ValorCatalogo, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    largo_mm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    ancho_mm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    m2_por_caja = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)

    class Meta:
        db_table = "productos_piso"


class DescuentoProducto(Auditoria):
    producto = models.OneToOneField(Producto, on_delete=models.PROTECT)
    precio_antes = models.DecimalField(max_digits=12, decimal_places=2)
    precio_ahora = models.DecimalField(max_digits=12, decimal_places=2)
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_fin = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "productos_descuento"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(precio_antes__gte=models.F("precio_ahora")),
                name="ck_descuento_precios_ordenados",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(fecha_inicio__isnull=True)
                    | models.Q(fecha_fin__isnull=True)
                    | models.Q(fecha_fin__gte=models.F("fecha_inicio"))
                ),
                name="ck_descuento_fechas_ordenadas",
            ),
        ]
