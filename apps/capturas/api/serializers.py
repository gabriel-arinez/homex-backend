from rest_framework import serializers


class CrearCapturaSerializer(serializers.Serializer):
    clave_idempotencia = serializers.UUIDField()
    proforma = serializers.IntegerField(min_value=1)
    proforma_detalle = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    texto = serializers.CharField(allow_blank=False, trim_whitespace=False)


class CapturaAceptadaSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    estado = serializers.CharField(read_only=True)
    intento_id = serializers.IntegerField(read_only=True)
    numero_intento = serializers.IntegerField(read_only=True)
    reutilizada = serializers.BooleanField(read_only=True)
