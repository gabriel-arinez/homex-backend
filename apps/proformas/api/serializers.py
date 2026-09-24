from rest_framework import serializers

from apps.proformas.models import DetalleProforma, EspecificacionMueble, Proforma


class EspecificacionMuebleSerializer(serializers.ModelSerializer):
    class Meta:
        model = EspecificacionMueble
        fields = "__all__"
        read_only_fields = ["proforma_detalle"]


class DetalleProformaSerializer(serializers.ModelSerializer):
    especificacion = EspecificacionMuebleSerializer(source="especificacionmueble", read_only=True)

    class Meta:
        model = DetalleProforma
        fields = [
            "id",
            "proforma",
            "tipo_item",
            "producto",
            "nombre",
            "descripcion",
            "cantidad",
            "unidad",
            "modo_calculo",
            "precio_unitario",
            "importe_negociado",
            "descuento",
            "precio_antes_snapshot",
            "precio_ahora_snapshot",
            "total",
            "especificacion",
        ]
        read_only_fields = ["proforma", "total", "precio_antes_snapshot", "precio_ahora_snapshot"]


class ProformaSerializer(serializers.ModelSerializer):
    detalles = DetalleProformaSerializer(many=True, read_only=True)

    class Meta:
        model = Proforma
        fields = [
            "id",
            "numero",
            "cliente",
            "vendedor",
            "estado",
            "titulo",
            "fecha",
            "plazo_entrega",
            "validez_oferta",
            "porcentaje_adelanto",
            "moneda",
            "subtotal",
            "descuento_total",
            "total",
            "observaciones",
            "prospecto_nombre",
            "prospecto_empresa",
            "prospecto_celular",
            "prospecto_direccion",
            "cliente_nombre_snapshot",
            "cliente_empresa_snapshot",
            "cliente_celular_snapshot",
            "cliente_direccion_snapshot",
            "created_by",
            "updated_by",
            "detalles",
        ]
        read_only_fields = [
            "numero",
            "vendedor",
            "estado",
            "fecha",
            "subtotal",
            "descuento_total",
            "total",
            "cliente_nombre_snapshot",
            "cliente_empresa_snapshot",
            "cliente_celular_snapshot",
            "cliente_direccion_snapshot",
            "created_by",
            "updated_by",
        ]


class CrearProformaSerializer(serializers.ModelSerializer):
    moneda_codigo = serializers.ChoiceField(choices=["BOB", "USD"], default="BOB", write_only=True)

    class Meta:
        model = Proforma
        fields = [
            "cliente",
            "titulo",
            "plazo_entrega",
            "validez_oferta",
            "porcentaje_adelanto",
            "moneda_codigo",
            "observaciones",
            "prospecto_nombre",
            "prospecto_empresa",
            "prospecto_celular",
            "prospecto_direccion",
        ]


class AprobarProformaRespuestaSerializer(serializers.Serializer):
    pedido_id = serializers.IntegerField(read_only=True)
    estado = serializers.CharField(read_only=True)


class CargaArchivoImagenSerializer(serializers.Serializer):
    archivo = serializers.ImageField()


class ArchivoAdjuntoSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    nombre = serializers.CharField(read_only=True)
    mime_type = serializers.CharField(read_only=True)
    tamano_bytes = serializers.IntegerField(read_only=True)
    url = serializers.URLField(read_only=True)
