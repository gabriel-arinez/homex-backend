import uuid

from django.conf import settings
from django.db import models


class GaleriaBorrador(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sesion = models.UUIDField()
    propietario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    actualizado = models.DateTimeField(auto_now=True)
    detalle = models.OneToOneField(
        "proformas.DetalleProforma", null=True, on_delete=models.CASCADE, related_name="galeria"
    )


class ArchivoAdjunto(models.Model):
    galeria = models.ForeignKey(
        GaleriaBorrador, null=True, on_delete=models.CASCADE, related_name="imagenes"
    )
    posicion = models.PositiveIntegerField(default=0)
    principal = models.BooleanField(default=False)
    variantes = models.JSONField(default=dict)
    dimensiones = models.JSONField(default=dict)
    sha256 = models.CharField(max_length=64, blank=True)
    privado = models.BooleanField(default=False)
    proforma = models.ForeignKey(
        "proformas.Proforma", null=True, blank=True, on_delete=models.CASCADE
    )
    proforma_detalle = models.ForeignKey(
        "proformas.DetalleProforma", null=True, blank=True, on_delete=models.CASCADE
    )
    nombre = models.CharField(max_length=255)
    nombre_storage = models.CharField(max_length=255)
    ruta_storage = models.TextField()
    mime_type = models.CharField(max_length=150, null=True, blank=True)
    tamano_bytes = models.BigIntegerField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "archivos_adjuntos"
        ordering = ["posicion", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["galeria"], condition=models.Q(principal=True), name="uq_galeria_portada"
            ),
            models.UniqueConstraint(
                fields=["proforma_detalle"],
                condition=models.Q(principal=True),
                name="uq_detalle_portada",
            ),
        ]
