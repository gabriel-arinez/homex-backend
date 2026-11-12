"""Shared read-only configurator projection DTOs for assisted and legacy review."""

from rest_framework import serializers


class ResolucionPendienteSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(
        choices=[
            "DIMENSION",
            "DIMENSIONES_NUEVAS",
            "COMPONENTE",
            "ATRIBUTO_GENERAL",
            "ESPESOR_SIN_COMPONENTE",
        ]
    )
    clave = serializers.CharField(required=False)
    uid = serializers.CharField(required=False)
    campo = serializers.CharField(required=False)
    cantidad = serializers.IntegerField(min_value=1, required=False)
    valor = serializers.CharField(required=False)


class PendienteAsistidaSerializer(serializers.Serializer):
    resolucion = ResolucionPendienteSerializer(required=False, allow_null=True)
    codigo = serializers.CharField()
    ruta = serializers.CharField(allow_blank=True)
    mensaje = serializers.CharField()
    total_negociado = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    moneda_codigo = serializers.ChoiceField(choices=["BOB", "USD"], required=False)


class ComercialAsistidaSerializer(serializers.Serializer):
    nombre = serializers.CharField()
    cantidad = serializers.IntegerField(allow_null=True)
    unidad_codigo = serializers.ChoiceField(choices=["PIEZA", "JUEGO"], allow_null=True)
    precio_unitario = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    descuento = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)


class EspecificacionAsistidaSerializer(serializers.Serializer):
    tipo_mueble = serializers.IntegerField(allow_null=True)
    datos_tecnicos = serializers.JSONField()
    observaciones = serializers.CharField(allow_null=True)


class PropuestaConfiguradorSerializer(serializers.Serializer):
    comercial = ComercialAsistidaSerializer()
    especificacion = EspecificacionAsistidaSerializer()
    pendientes = PendienteAsistidaSerializer(many=True)
