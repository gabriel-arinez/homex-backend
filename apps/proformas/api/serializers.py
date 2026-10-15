from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.catalogo.models import ValorCatalogo
from apps.clientes.models import Cliente
from apps.proformas.models import DetalleProforma, EspecificacionMueble, Proforma
from apps.proformas.revision import revision_proforma
from apps.proformas.validacion_tecnica import validar_datos_tecnicos


class ValorCatalogoResumenSerializer(serializers.ModelSerializer):
    class Meta:
        model = ValorCatalogo
        fields = ["id", "codigo", "nombre"]
        read_only_fields = fields


class ClienteResumenProformaSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nombre = serializers.CharField(allow_null=True, allow_blank=True)
    empresa = serializers.CharField(allow_null=True, allow_blank=True)
    celular = serializers.CharField(allow_null=True, allow_blank=True)


class ProformaFiltrosListadoSerializer(serializers.Serializer):
    search = serializers.CharField(
        required=False,
        allow_blank=False,
        help_text="Número de proforma, título o datos del cliente.",
    )
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
            "datos_tecnicos",
            "observaciones",
        ]
        read_only_fields = ["id", "proforma_detalle", "tipo_mueble_info"]

    def validate_datos_tecnicos(self, datos):
        return validar_datos_tecnicos(datos)


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
            "familia_producto",
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
    revision = serializers.SerializerMethodField()

    class Meta:
        model = Proforma
        fields = [
            "id",
            "numero",
            "revision",
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
            "revision",
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

    @extend_schema_field(serializers.CharField())
    def get_revision(self, proforma):
        return revision_proforma(proforma)

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


class ClienteNuevoProformaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = [
            "tipo_cliente",
            "nombres",
            "apellidos",
            "empresa",
            "celular",
            "direccion",
            "observaciones",
        ]


class DetalleIntegralSerializer(DetalleProformaSerializer):
    id = serializers.IntegerField(required=False)
    especificacion = EspecificacionMuebleSerializer(required=False, allow_null=True)

    class Meta(DetalleProformaSerializer.Meta):
        read_only_fields = [
            "proforma",
            "tipo_item_info",
            "unidad_info",
            "total",
            "precio_antes_snapshot",
            "precio_ahora_snapshot",
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get("modo_calculo", "PRECIO_UNITARIO") != "PRECIO_UNITARIO":
            if not (attrs.get("id") and attrs.get("modo_calculo") == "TOTAL_NEGOCIADO"):
                raise serializers.ValidationError(
                    {"modo_calculo": "Los ítems nuevos sólo admiten PRECIO_UNITARIO."}
                )
        cantidad = attrs.get("cantidad")
        precio = attrs.get("precio_unitario")
        descuento = attrs.get("descuento")
        if cantidad is not None and precio is not None and descuento is not None:
            if descuento > cantidad * precio:
                raise serializers.ValidationError(
                    {"descuento": "No puede superar el importe bruto de la línea."}
                )
        return attrs


class ProformaIntegralSerializer(serializers.Serializer):
    clave_idempotencia = serializers.UUIDField()
    revision_esperada = serializers.CharField(required=False, min_length=64, max_length=64)
    emitir = serializers.BooleanField(default=False)
    cliente = serializers.PrimaryKeyRelatedField(
        queryset=Cliente.objects.filter(activo=True), required=False, allow_null=True
    )
    cliente_nuevo = ClienteNuevoProformaSerializer(required=False, allow_null=True)
    titulo = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=250
    )
    plazo_entrega = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=100
    )
    validez_oferta = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    porcentaje_adelanto = serializers.DecimalField(
        required=False, allow_null=True, max_digits=5, decimal_places=2, min_value=0, max_value=100
    )
    moneda_codigo = serializers.ChoiceField(choices=["BOB", "USD"])
    observaciones = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    prospecto_nombre = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    prospecto_empresa = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    prospecto_celular = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    prospecto_direccion = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    detalles = DetalleIntegralSerializer(many=True, required=False, default=list)

    def validate(self, attrs):
        if self.context.get("actualizacion") and not attrs.get("revision_esperada"):
            raise serializers.ValidationError(
                {"revision_esperada": "Debes recargar la proforma antes de modificarla."}
            )
        if attrs.get("cliente") and attrs.get("cliente_nuevo"):
            raise serializers.ValidationError(
                {"cliente_nuevo": "Seleccione un cliente existente o registre uno nuevo, no ambos."}
            )
        detalles = attrs.get("detalles", [])
        productos = [detalle["producto"].id for detalle in detalles if detalle.get("producto")]
        if len(productos) != len(set(productos)):
            raise serializers.ValidationError(
                {"detalles": "Una variante de catálogo no puede repetirse en la proforma."}
            )
        if attrs.get("emitir"):
            if not (attrs.get("cliente") or attrs.get("cliente_nuevo")):
                raise serializers.ValidationError(
                    {"cliente": "Debe seleccionar o registrar un cliente antes de emitir."}
                )
            if not detalles:
                raise serializers.ValidationError(
                    {"detalles": "Debe agregar al menos una línea antes de emitir."}
                )
        return attrs


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
