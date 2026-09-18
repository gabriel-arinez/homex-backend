from rest_framework import serializers

from apps.proformas.models import Proforma


class ProformaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proforma
        fields = (
            "id",
            "numero",
            "cliente",
            "vendedor",
            "estado",
            "moneda",
            "titulo",
            "fecha",
            "subtotal",
            "descuento_total",
            "total",
        )
        read_only_fields = ("numero", "vendedor", "subtotal", "descuento_total", "total")
