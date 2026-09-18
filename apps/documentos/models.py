from django.conf import settings
from django.db import models


class ArchivoAdjunto(models.Model):
    proforma = models.ForeignKey("proformas.Proforma", on_delete=models.PROTECT)
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
