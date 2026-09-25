from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.catalogo.models import ValorCatalogo
from apps.proformas.models import DetalleProforma, EspecificacionMueble, Proforma


class ValorCatalogoResumenSerializer(serializers.ModelSerializer):
    class Meta:
        model = ValorCatalogo
        fields = ["id", "codigo", "nombre"]
        read_only_fields = fields


class ClienteResumenProformaSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nombre = serializers.CharField(allow_blank=True)
    empresa = serializers.CharField(allow_null=True, allow_blank=True)
    celular = serializers.CharField(allow_null=True, allow_blank=True)


class ProformaFiltrosListadoSerializer(serializers.Serializer):
    estado = serializers.CharField(required=False, max_length=80)
    moneda = serializers.CharField(required=False, max_length=80)
    cliente = serializers.IntegerField(required=False, min_value=1)
    fecha_desde = serializers.DateField(required=False)
    fecha_hasta = serializers.DateField(required=False)

    def validate(self, attrs):
        desde = attrs.get("fecha_desde")
        hasta = attrs.get("fecha_hasta")
        if desde and hasta and desde > hasta:
            raise serializers.ValidationError(
                {"fecha_hasta": "Debe ser igual o posterior a fecha_desde."}
            )
        return attrs


class EspecificacionMuebleSerializer(serializers.ModelSerializer):
    tipo_mueble_info = ValorCatalogoResumenSerializer(
        source="tipo_mueble",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = EspecificacionMueble
        fields = [
            "id",
            "proforma_detalle",
            "tipo_mueble",
            "tipo_mueble_info",
            "schema_version",
            "espesor",
            "color_principal",
            "color_secundario",
            "dimensiones",
            "accesorios",
            "observaciones",
        ]
        read_only_fields = ["id", "proforma_detalle", "tipo_mueble_info"]


class DetalleProformaSerializer(serializers.ModelSerializer):
    especificacion = EspecificacionMuebleSerializer(source="especificacionmueble", read_only=True)
    tipo_item_info = ValorCatalogoResumenSerializer(source="tipo_item", read_only=True)
    unidad_info = ValorCatalogoResumenSerializer(source="unidad", read_only=True)

    class Meta:
        model = DetalleProforma
        fields = [
            "id",
            "proforma",
            "tipo_item",
            "tipo_item_info",
            "producto",
            "nombre",
            "descripcion",
            "cantidad",
            "unidad",
            "unidad_info",
            "modo_calculo",
            "precio_unitario",
            "importe_negociado",
            "descuento",
            "precio_antes_snapshot",
            "precio_ahora_snapshot",
            "total",
            "especificacion",
        ]
        read_only_fields = [
            "proforma",
            "tipo_item_info",
            "unidad_info",
            "total",
            "precio_antes_snapshot",
            "precio_ahora_snapshot",
        ]


class ProformaSerializer(serializers.ModelSerializer):
    detalles = DetalleProformaSerializer(many=True, read_only=True)
    estado_info = ValorCatalogoResumenSerializer(source="estado", read_only=True)
    moneda_info = ValorCatalogoResumenSerializer(source="moneda", read_only=True)
    cliente_resumen = serializers.SerializerMethodField()

    class Meta:
        model = Proforma
        fields = [
            "id",
            "numero",
            "cliente",
            "cliente_resumen",
            "vendedor",
            "estado",
            "estado_info",
            "titulo",
            "fecha",
            "plazo_entrega",
            "validez_oferta",
            "porcentaje_adelanto",
            "moneda",
            "moneda_info",
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
            "cliente_resumen",
            "vendedor",
            "estado",
            "estado_info",
            "fecha",
            "moneda_info",
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

    @extend_schema_field(ClienteResumenProformaSerializer(allow_null=True))
    def get_cliente_resumen(self, proforma):
        if proforma.cliente_id is None:
            return None

        cliente = proforma.cliente
        nombre_actual = " ".join(
            value.strip()
            for value in [cliente.nombres or "", cliente.apellidos or ""]
            if value.strip()
        )
        tiene_snapshot = any(
            value is not None
            for value in [
                proforma.cliente_nombre_snapshot,
                proforma.cliente_empresa_snapshot,
                proforma.cliente_celular_snapshot,
            ]
        )

        return {
            "id": proforma.cliente_id,
            "nombre": proforma.cliente_nombre_snapshot if tiene_snapshot else nombre_actual,
            "empresa": proforma.cliente_empresa_snapshot if tiene_snapshot else cliente.empresa,
            "celular": proforma.cliente_celular_snapshot if tiene_snapshot else cliente.celular,
        }


class ProformaListadoSerializer(ProformaSerializer):
    class Meta(ProformaSerializer.Meta):
        fields = [
            "id",
            "numero",
            "cliente",
            "cliente_resumen",
            "vendedor",
            "estado",
            "estado_info",
            "titulo",
            "fecha",
            "plazo_entrega",
            "validez_oferta",
            "porcentaje_adelanto",
            "moneda",
            "moneda_info",
            "subtotal",
            "descuento_total",
            "total",
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
