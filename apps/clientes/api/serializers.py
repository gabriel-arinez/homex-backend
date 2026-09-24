from rest_framework import serializers

from apps.clientes.models import Cliente


class ClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = [
            "id",
            "tipo_cliente",
            "nombres",
            "apellidos",
            "empresa",
            "celular",
            "direccion",
            "observaciones",
            "activo",
            "created_by",
            "updated_by",
        ]
        read_only_fields = ["created_by", "updated_by"]
