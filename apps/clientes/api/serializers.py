from rest_framework import serializers

from apps.catalogo.api.serializers import ValorCatalogoPublicoSerializer
from apps.clientes.models import Cliente
from apps.clientes.revision import revision_cliente
from drf_spectacular.utils import extend_schema_field
from apps.clientes.validacion import tipos_cliente_activos, validar_identidad_cliente


class ClienteSerializer(serializers.ModelSerializer):
    tipo_cliente = serializers.PrimaryKeyRelatedField(queryset=tipos_cliente_activos())
    tipo_cliente_info = ValorCatalogoPublicoSerializer(source="tipo_cliente", read_only=True)
    revision = serializers.SerializerMethodField()

    class Meta:
        model = Cliente
        fields = [
            "id",
            "tipo_cliente",
            "tipo_cliente_info",
            "revision",
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
        read_only_fields = ["tipo_cliente_info", "revision", "created_by", "updated_by"]

    @extend_schema_field(serializers.CharField())
    def get_revision(self, instance):
        return revision_cliente(instance)

    def validate(self, attrs):
        return validar_identidad_cliente(attrs, instance=self.instance)


class ClienteFiltrosListadoSerializer(serializers.Serializer):
    activo = serializers.BooleanField(required=False)
    tipo_cliente = serializers.IntegerField(required=False, min_value=1)
