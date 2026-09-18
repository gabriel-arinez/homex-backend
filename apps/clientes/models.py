from django.conf import settings
from django.db import models


class Cliente(models.Model):
    tipo_cliente = models.ForeignKey("catalogo.ValorCatalogo", on_delete=models.PROTECT)
    nombres = models.CharField(max_length=150, null=True, blank=True)
    apellidos = models.CharField(max_length=150, null=True, blank=True)
    empresa = models.CharField(max_length=200, null=True, blank=True)
    celular = models.CharField(max_length=40, null=True, blank=True)
    direccion = models.TextField(null=True, blank=True)
    observaciones = models.TextField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "clientes"
