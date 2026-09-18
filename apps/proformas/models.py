from django.conf import settings
from django.db import models


class Proforma(models.Model):
    numero = models.BigIntegerField(unique=True)
    cliente = models.ForeignKey("clientes.Cliente", null=True, blank=True, on_delete=models.PROTECT)
    vendedor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    estado = models.ForeignKey("catalogo.ValorCatalogo", on_delete=models.PROTECT, related_name="+")
    titulo = models.CharField(max_length=250, null=True, blank=True)
    fecha = models.DateField()
    plazo_entrega = models.CharField(max_length=100, null=True, blank=True)
    validez_oferta = models.SmallIntegerField(null=True, blank=True)
    porcentaje_adelanto = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    moneda = models.ForeignKey("catalogo.ValorCatalogo", on_delete=models.PROTECT, related_name="+")
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    descuento_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    observaciones = models.TextField(null=True, blank=True)
    prospecto_nombre = models.CharField(max_length=250, null=True, blank=True)
    prospecto_empresa = models.CharField(max_length=200, null=True, blank=True)
    prospecto_celular = models.CharField(max_length=40, null=True, blank=True)
    prospecto_direccion = models.TextField(null=True, blank=True)
    cliente_nombre_snapshot = models.CharField(max_length=300, null=True, blank=True)
    cliente_empresa_snapshot = models.CharField(max_length=200, null=True, blank=True)
    cliente_celular_snapshot = models.CharField(max_length=40, null=True, blank=True)
    cliente_direccion_snapshot = models.TextField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "proformas"


class DetalleProforma(models.Model):
    proforma = models.ForeignKey(Proforma, on_delete=models.PROTECT, related_name="detalles")
    tipo_item = models.ForeignKey(
        "catalogo.ValorCatalogo", on_delete=models.PROTECT, related_name="+"
    )
    producto = models.ForeignKey(
        "catalogo.Producto", null=True, blank=True, on_delete=models.PROTECT
    )
    nombre = models.CharField(max_length=250)
    descripcion = models.TextField(null=True, blank=True)
    cantidad = models.IntegerField()
    unidad = models.ForeignKey("catalogo.ValorCatalogo", on_delete=models.PROTECT, related_name="+")
    modo_calculo = models.CharField(max_length=20, default="PRECIO_UNITARIO")
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    importe_negociado = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    descuento = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    precio_antes_snapshot = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    precio_ahora_snapshot = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        db_table = "proformas_detalle"
        constraints = [
            models.UniqueConstraint(fields=["proforma", "id"], name="uq_proforma_detalle_par"),
            models.CheckConstraint(
                condition=models.Q(modo_calculo__in=["PRECIO_UNITARIO", "TOTAL_NEGOCIADO"]),
                name="ck_detalle_modo_calculo",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(modo_calculo="PRECIO_UNITARIO", importe_negociado__isnull=True)
                    | models.Q(modo_calculo="TOTAL_NEGOCIADO", importe_negociado__isnull=False)
                ),
                name="ck_detalle_importe_negociado",
            ),
        ]


class EspecificacionMueble(models.Model):
    proforma_detalle = models.OneToOneField(DetalleProforma, on_delete=models.CASCADE)
    tipo_mueble = models.ForeignKey(
        "catalogo.ValorCatalogo", null=True, blank=True, on_delete=models.PROTECT
    )
    schema_version = models.SmallIntegerField(default=1)
    espesor = models.JSONField(null=True, blank=True)
    color_principal = models.CharField(max_length=150, null=True, blank=True)
    color_secundario = models.CharField(max_length=150, null=True, blank=True)
    dimensiones = models.JSONField(null=True, blank=True)
    accesorios = models.JSONField(null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "especificaciones_mueble"
