from pathlib import Path

from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.capturas.audio import SUFIJOS_AUDIO


@extend_schema_field(OpenApiTypes.BINARY)
class AudioCapturaField(serializers.FileField):
    pass


class CrearCapturaSerializer(serializers.Serializer):
    clave_idempotencia = serializers.UUIDField()
    proforma = serializers.IntegerField(min_value=1)
    proforma_detalle = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    texto = serializers.CharField(allow_blank=False, trim_whitespace=False, required=False)
    audio = AudioCapturaField(required=False, write_only=True)

    def validate(self, attrs):
        texto = attrs.get("texto")
        audio = attrs.get("audio")
        if bool(texto) == bool(audio):
            raise serializers.ValidationError("Envíe exactamente uno de texto o audio.")
        if audio:
            if audio.size <= 0 or audio.size > settings.HOMEX_AUDIO_MAX_BYTES:
                raise serializers.ValidationError({"audio": "Tamaño de audio no admitido."})
            if Path(audio.name).suffix.lower() not in SUFIJOS_AUDIO:
                raise serializers.ValidationError({"audio": "Formato de audio no admitido."})
            if audio.content_type and not audio.content_type.startswith("audio/"):
                raise serializers.ValidationError({"audio": "El MIME debe corresponder a audio."})
        return attrs


class CapturaAceptadaSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    estado = serializers.CharField(read_only=True)
    intento_id = serializers.IntegerField(read_only=True)
    numero_intento = serializers.IntegerField(read_only=True)
    reutilizada = serializers.BooleanField(read_only=True)


class CrearCapturaTextoSerializer(serializers.Serializer):
    """Esquema OpenAPI exacto para recepción JSON/form de texto."""

    clave_idempotencia = serializers.UUIDField()
    proforma = serializers.IntegerField(min_value=1)
    proforma_detalle = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    texto = serializers.CharField(allow_blank=False, trim_whitespace=False)


class CrearCapturaMultipartSerializer(CrearCapturaSerializer):
    """Esquema OpenAPI multipart; mantiene la regla runtime de exactamente un input."""

    pass


class EstrictoSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        desconocidos = set(data) - set(self.fields)
        if desconocidos:
            raise serializers.ValidationError(
                {campo: "Campo no admitido." for campo in sorted(desconocidos)}
            )
        return super().to_internal_value(data)


class ItemCorregidoSerializer(EstrictoSerializer):
    nombre = serializers.CharField(max_length=250)
    espesor = serializers.JSONField(required=False, allow_null=True)
    color_principal = serializers.CharField(max_length=150, required=False, allow_null=True)
    color_secundario = serializers.CharField(max_length=150, required=False, allow_null=True)
    dimensiones = serializers.JSONField(required=False, allow_null=True)
    accesorios = serializers.JSONField(required=False, allow_null=True)
    cantidad = serializers.IntegerField(min_value=1)
    observaciones = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        espesor = attrs.get("espesor")
        if espesor is not None and (
            not isinstance(espesor, dict)
            or set(espesor) != {"espesor"}
            or not isinstance(espesor["espesor"], str)
        ):
            raise serializers.ValidationError(
                {"espesor": 'Debe tener la forma {"espesor": "valor con unidad"}.'}
            )
        dimensiones = attrs.get("dimensiones")
        ejes = {"ancho", "alto", "profundidad", "largo", "diametro"}
        if dimensiones is not None and (
            not isinstance(dimensiones, dict)
            or any(clave not in ejes for clave in dimensiones)
            or any(not isinstance(valor, str) for valor in dimensiones.values())
        ):
            raise serializers.ValidationError(
                {"dimensiones": "Use ejes V1 con valores de texto y unidad."}
            )
        accesorios = attrs.get("accesorios")
        if accesorios is not None and (
            not isinstance(accesorios, list)
            or any(not isinstance(valor, str) for valor in accesorios)
        ):
            raise serializers.ValidationError(
                {"accesorios": "Debe ser un array de textos en schema V1."}
            )
        return attrs


class LineaComercialHITLSerializer(EstrictoSerializer):
    tipo_item_id = serializers.IntegerField(min_value=1)
    unidad_id = serializers.IntegerField(min_value=1)
    modo_calculo = serializers.ChoiceField(choices=["PRECIO_UNITARIO", "TOTAL_NEGOCIADO"])
    precio_unitario = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False, allow_null=True
    )
    importe_negociado = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=0, required=False, allow_null=True
    )
    descripcion = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    tipo_mueble_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class ConfirmarCapturaSerializer(EstrictoSerializer):
    intento_id = serializers.IntegerField(min_value=1)
    item_ia_id = serializers.IntegerField(min_value=1)
    item_corregido = ItemCorregidoSerializer()
    linea_comercial = LineaComercialHITLSerializer()


class ItemIASerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    nombre = serializers.CharField(read_only=True, allow_null=True)
    espesor = serializers.JSONField(read_only=True, allow_null=True)
    color_principal = serializers.CharField(read_only=True, allow_null=True)
    color_secundario = serializers.CharField(read_only=True, allow_null=True)
    dimensiones = serializers.JSONField(read_only=True, allow_null=True)
    accesorios = serializers.JSONField(read_only=True, allow_null=True)
    cantidad = serializers.IntegerField(read_only=True, allow_null=True)
    precio_total = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, allow_null=True
    )
    observaciones = serializers.CharField(read_only=True, allow_null=True)


class CapturaRevisionSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    proforma = serializers.IntegerField(source="proforma_id", read_only=True)
    proforma_detalle = serializers.IntegerField(source="proforma_detalle_id", read_only=True)
    estado = serializers.CharField(read_only=True)
    texto_transcrito = serializers.CharField(read_only=True, allow_null=True)
    intento_id = serializers.SerializerMethodField()
    item_ia = serializers.SerializerMethodField()
    incorporada = serializers.SerializerMethodField()

    def _intento(self, obj):
        return (
            obj.intentocaptura_set.filter(estado="FINALIZADO")
            .select_related("itemia")
            .order_by("-numero_intento")
            .first()
        )

    @extend_schema_field(OpenApiTypes.INT)
    def get_intento_id(self, obj) -> int | None:
        intento = self._intento(obj)
        return intento.id if intento else None

    @extend_schema_field(ItemIASerializer(allow_null=True))
    def get_item_ia(self, obj) -> dict | None:
        intento = self._intento(obj)
        if intento is None or not hasattr(intento, "itemia"):
            return None
        return ItemIASerializer(intento.itemia).data

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_incorporada(self, obj) -> bool:
        return obj.proforma_detalle_id is not None


class ConfirmacionHITLRespuestaSerializer(serializers.Serializer):
    captura_id = serializers.IntegerField(read_only=True)
    detalle_id = serializers.IntegerField(read_only=True)
    item_humano_id = serializers.IntegerField(read_only=True)
    evaluacion_id = serializers.IntegerField(read_only=True)
    proforma_estado = serializers.CharField(read_only=True)
