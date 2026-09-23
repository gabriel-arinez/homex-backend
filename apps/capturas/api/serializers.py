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
