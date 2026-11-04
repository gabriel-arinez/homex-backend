from rest_framework import serializers


class ImagenGaleriaSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    sha256 = serializers.CharField(read_only=True)
    nombre = serializers.CharField(read_only=True)
    posicion = serializers.IntegerField(read_only=True)
    principal = serializers.BooleanField(read_only=True)
    url = serializers.CharField(read_only=True)
    variantes = serializers.DictField(child=serializers.CharField(), read_only=True)
    dimensiones = serializers.DictField(child=serializers.IntegerField(), read_only=True)


class GaleriaRespuestaSerializer(serializers.Serializer):
    imagenes = ImagenGaleriaSerializer(many=True, read_only=True)
    limite = serializers.IntegerField(read_only=True)


class ModificarGaleriaSerializer(serializers.Serializer):
    orden = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False)
    principal = serializers.IntegerField(min_value=1, required=False)
    eliminar = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs):
        if len(attrs) != 1:
            raise serializers.ValidationError("Envía exactamente una acción de galería.")
        return attrs


class CargaGaleriaSerializer(serializers.Serializer):
    archivo = serializers.FileField()


class IdentificadorGaleriaSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
