from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.timezone import localdate

from apps.catalogo.models import Producto, ValorCatalogo
from apps.clientes.models import Cliente


class Proforma(models.Model):
    numero = models.BigIntegerField(unique=True, null=True, editable=False)
    cliente = models.ForeignKey(Cliente, null=True, blank=True, on_delete=models.PROTECT)
    vendedor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="proformas_vendidas"
    )
    estado = models.ForeignKey(
        ValorCatalogo, on_delete=models.PROTECT, related_name="proformas_por_estado"
    )
    titulo = models.CharField(max_length=250, blank=True)
    fecha = models.DateField(default=localdate)
    plazo_entrega = models.CharField(max_length=100, blank=True)
    vigencia_oferta = models.SmallIntegerField(null=True, blank=True)
    porcentaje_anticipo = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    moneda = models.ForeignKey(
        ValorCatalogo, on_delete=models.PROTECT, related_name="proformas_por_moneda"
    )
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    descuento_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    observaciones = models.TextField(blank=True)
    nombre_prospecto = models.CharField(max_length=250, blank=True)
    empresa_prospecto = models.CharField(max_length=200, blank=True)
    celular_prospecto = models.CharField(max_length=40, blank=True)
    direccion_prospecto = models.TextField(blank=True)
    cliente_nombre_snapshot = models.CharField(max_length=300, blank=True)
    cliente_empresa_snapshot = models.CharField(max_length=200, blank=True)
    cliente_celular_snapshot = models.CharField(max_length=40, blank=True)
    cliente_direccion_snapshot = models.TextField(blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="proformas_creadas",
    )
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="proformas_actualizadas",
    )

    class Meta:
        db_table = "proformas"
        constraints = [
            models.CheckConstraint(
                condition=Q(vigencia_oferta__isnull=True) | Q(vigencia_oferta__gte=0),
                name="ck_proforma_validez_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(porcentaje_anticipo__isnull=True)
                | (Q(porcentaje_anticipo__gte=0) & Q(porcentaje_anticipo__lte=100)),
                name="ck_proforma_adelanto",
            ),
            models.CheckConstraint(
                condition=Q(subtotal__gte=0) & Q(descuento_total__gte=0) & Q(total__gte=0),
                name="ck_proforma_importes",
            ),
        ]


class DetalleProforma(models.Model):
    class CalculationMode(models.TextChoices):
        UNIT = "PRECIO_UNITARIO"
        NEGOTIATED = "TOTAL_NEGOCIADO"

    proforma = models.ForeignKey(Proforma, on_delete=models.PROTECT, related_name="detalles")
    tipo_item = models.ForeignKey(
        ValorCatalogo, on_delete=models.PROTECT, related_name="proforma_detalles_by_tipo"
    )
    producto = models.ForeignKey(Producto, null=True, blank=True, on_delete=models.PROTECT)
    nombre = models.CharField(max_length=250)
    descripcion = models.TextField(blank=True)
    cantidad = models.IntegerField()
    unidad = models.ForeignKey(
        ValorCatalogo, on_delete=models.PROTECT, related_name="proforma_detalles_by_unidad"
    )
    modo_calculo = models.CharField(
        max_length=20, choices=CalculationMode.choices, default=CalculationMode.UNIT
    )
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    monto_negociado = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    descuento = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        db_table = "proformas_detalle"
        constraints = [
            models.CheckConstraint(
                condition=Q(cantidad__gt=0), name="ck_detalle_cantidad_positive"
            ),
            models.CheckConstraint(
                condition=Q(precio_unitario__gte=0), name="ck_detalle_precio_nonnegative"
            ),
        ]


class EspecificacionMueble(models.Model):
    detalle = models.OneToOneField(
        DetalleProforma,
        on_delete=models.CASCADE,
        related_name="especificacion_mueble",
        db_column="proforma_detalle_id",
    )
    tipo_mueble = models.ForeignKey(
        ValorCatalogo, null=True, blank=True, on_delete=models.PROTECT
    )
    version_schema = models.SmallIntegerField(default=1)
    espesor = models.JSONField(null=True, blank=True)
    color_primario = models.CharField(max_length=150, blank=True)
    color_secundario = models.CharField(max_length=150, blank=True)
    dimensiones = models.JSONField(null=True, blank=True)
    accesorios = models.JSONField(null=True, blank=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        db_table = "especificaciones_mueble"
        constraints = [
            models.CheckConstraint(
                condition=Q(version_schema=1), name="ck_especificacion_version_schema"
            )
        ]
