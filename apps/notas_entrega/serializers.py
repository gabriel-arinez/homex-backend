from rest_framework import serializers

from apps.notas_entrega.models import NotaEntrega


class NotaEntregaSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotaEntrega
        fields = ("id", "pedido", "vendedor", "numero", "fecha")
        read_only_fields = ("vendedor", "numero", "fecha")
