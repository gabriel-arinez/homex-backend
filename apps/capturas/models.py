from django.conf import settings
from django.db import models


class Captura(models.Model):
    proforma = models.ForeignKey("proformas.Proforma", on_delete=models.PROTECT)
    proforma_detalle = models.ForeignKey(
        "proformas.DetalleProforma", null=True, blank=True, on_delete=models.PROTECT
    )
    vendedor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    clave_idempotencia = models.UUIDField(unique=True)
    estado = models.CharField(max_length=20, default="PENDIENTE")
    capturado_at = models.DateTimeField()
    texto_transcrito = models.TextField(null=True, blank=True)
    texto_normalizado = models.TextField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "capturas"


class IntentoCaptura(models.Model):
    captura = models.ForeignKey(Captura, on_delete=models.CASCADE)
    numero_intento = models.IntegerField()
    estado = models.CharField(max_length=20, default="PENDIENTE")
    etapa_alcanzada = models.CharField(max_length=20, null=True, blank=True)
    input_hash = models.CharField(max_length=64, null=True, blank=True)
    modelo_asr_version = models.CharField(max_length=150, null=True, blank=True)
    modelo_nlp_version = models.CharField(max_length=150, null=True, blank=True)
    inicio_at = models.DateTimeField()
    fin_at = models.DateTimeField(null=True, blank=True)
    latencia_total_ms = models.IntegerField(null=True, blank=True)
    latencia_asr_ms = models.IntegerField(null=True, blank=True)
    latencia_nlp_ms = models.IntegerField(null=True, blank=True)
    error_codigo = models.CharField(max_length=100, null=True, blank=True)
    error_detalle = models.TextField(null=True, blank=True)
    labels_detectados = models.JSONField(null=True, blank=True)
    resultado_raw = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "intentos_captura"
        constraints = [
            models.UniqueConstraint(
                fields=["captura", "numero_intento"], name="uq_intento_captura_numero"
            )
        ]


class TrabajoOutbox(models.Model):
    intento = models.OneToOneField(IntentoCaptura, on_delete=models.CASCADE)
    tipo = models.CharField(max_length=60, default="PROCESAR_CAPTURA")
    clave_unica = models.CharField(max_length=180, unique=True)
    disponible_at = models.DateTimeField()
    publicado_at = models.DateTimeField(null=True, blank=True)
    intentos_publicacion = models.IntegerField(default=0)
    ultimo_error = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "trabajos_outbox"


class ItemIA(models.Model):
    intento = models.OneToOneField(IntentoCaptura, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=250, null=True, blank=True)
    espesor = models.JSONField(null=True, blank=True)
    color_principal = models.CharField(max_length=150, null=True, blank=True)
    color_secundario = models.CharField(max_length=150, null=True, blank=True)
    dimensiones = models.JSONField(null=True, blank=True)
    accesorios = models.JSONField(null=True, blank=True)
    cantidad = models.IntegerField(null=True, blank=True)
    precio_total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "items_ia"


class ItemHumano(models.Model):
    item_ia = models.OneToOneField(ItemIA, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=250)
    espesor = models.JSONField(null=True, blank=True)
    color_principal = models.CharField(max_length=150, null=True, blank=True)
    color_secundario = models.CharField(max_length=150, null=True, blank=True)
    dimensiones = models.JSONField(null=True, blank=True)
    accesorios = models.JSONField(null=True, blank=True)
    cantidad = models.IntegerField(null=True, blank=True)
    precio_total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)
    revisor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    revisado_at = models.DateTimeField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "items_humano"


class EvaluacionNLP(models.Model):
    item_humano = models.OneToOneField(ItemHumano, on_delete=models.CASCADE)
    version_metrica = models.CharField(max_length=50, default="V1")
    inicio_revision_at = models.DateTimeField(null=True, blank=True)
    fin_revision_at = models.DateTimeField(null=True, blank=True)
    tiempo_revision_ms = models.IntegerField(null=True, blank=True)
    campos_totales = models.IntegerField(default=0)
    campos_corregidos = models.IntegerField(default=0)
    campos_agregados = models.IntegerField(default=0)
    campos_eliminados = models.IntegerField(default=0)
    precision_item = models.DecimalField(max_digits=6, decimal_places=5, null=True, blank=True)
    precision_campo = models.DecimalField(max_digits=6, decimal_places=5, null=True, blank=True)
    evaluated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "evaluaciones_nlp"


class MedicionProceso(models.Model):
    proforma = models.ForeignKey("proformas.Proforma", on_delete=models.PROTECT)
    metodo = models.ForeignKey("catalogo.ValorCatalogo", on_delete=models.PROTECT)
    operador = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    protocolo_version = models.CharField(max_length=80, null=True, blank=True)
    inicio_at = models.DateTimeField()
    fin_at = models.DateTimeField()
    tiempo_total_ms = models.IntegerField()
    num_items = models.IntegerField(default=1)
    observaciones = models.TextField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "mediciones_proceso"
