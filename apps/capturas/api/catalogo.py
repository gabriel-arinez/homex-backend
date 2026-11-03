from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from apps.capturas.api.asistidas import CapturaAsistidaViewSet, CrearAsistidaSerializer
from apps.capturas.api.serializers import CapturaAceptadaSerializer
from apps.capturas.audio import AudioTemporalInvalido
from apps.capturas.catalogo import MODO, recibir_catalogo, resultado_catalogo
from apps.capturas.models import Captura
from apps.core.permissions import PuedeCrearProducto


class CrearCatalogoSerializer(CrearAsistidaSerializer):
    categoria = serializers.ChoiceField(choices=["SILLA", "PISO_FLOTANTE", "OTRO"])
    texto = serializers.CharField(max_length=20000, required=False, trim_whitespace=False)
    proforma = None
    moneda_codigo = None


class CamposCatalogoSerializer(serializers.Serializer):
    nombre = serializers.CharField(required=False)
    observaciones = serializers.CharField(required=False)
    precio_lista = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    unidad_stock = serializers.IntegerField(required=False)
    marca = serializers.IntegerField(required=False)
    modelo = serializers.CharField(required=False)
    color_primario = serializers.IntegerField(required=False)
    color_secundario = serializers.IntegerField(required=False)
    especificaciones = serializers.JSONField(required=False)
    tipo = serializers.IntegerField(required=False)
    material = serializers.IntegerField(required=False)
    diseno = serializers.IntegerField(required=False)
    acabado = serializers.IntegerField(required=False)
    espesor_mm = serializers.DecimalField(max_digits=8, decimal_places=2, required=False)
    largo_mm = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    ancho_mm = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    m2_por_caja = serializers.DecimalField(max_digits=10, decimal_places=4, required=False)


class EvidenciaCatalogoSerializer(serializers.Serializer):
    candidate_id = serializers.CharField()
    label = serializers.CharField()
    start = serializers.IntegerField()
    end = serializers.IntegerField()
    text = serializers.CharField()
    decision = serializers.ChoiceField(choices=["ACCEPTED", "REJECTED", "UNRESOLVED"])
    normalized_value = serializers.JSONField()
    reason = serializers.CharField(allow_null=True)


class PropuestaCatalogoSerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=["SILLA", "PISO_FLOTANTE", "OTRO"])
    fields = CamposCatalogoSerializer()
    evidence = EvidenciaCatalogoSerializer(many=True)
    warnings = serializers.ListField(child=serializers.CharField())
    unrecognized = serializers.ListField(child=serializers.CharField())
    version = serializers.CharField()


class ResultadoCatalogoSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    estado = serializers.CharField()
    categoria = serializers.ChoiceField(choices=["SILLA", "PISO_FLOTANTE", "OTRO"])
    texto_transcrito_original = serializers.CharField(allow_null=True)
    propuesta = PropuestaCatalogoSerializer(allow_null=True)
    error_codigo = serializers.CharField(allow_null=True)


class CapturaCatalogoViewSet(CapturaAsistidaViewSet):
    permission_classes = [PuedeCrearProducto]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Captura.objects.none()
        return Captura.objects.filter(modo_captura=MODO, vendedor=self.request.user)

    def get_serializer_class(self):
        return ResultadoCatalogoSerializer if self.action == "retrieve" else CrearCatalogoSerializer

    @extend_schema(request=CrearCatalogoSerializer, responses={202: CapturaAceptadaSerializer})
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = recibir_catalogo(actor=request.user, **serializer.validated_data)
        except AudioTemporalInvalido as exc:
            raise serializers.ValidationError({"audio": str(exc)}) from exc
        return Response(
            {
                "id": result.captura.id,
                "estado": result.captura.estado,
                "intento_id": result.intento.id,
                "numero_intento": result.intento.numero_intento,
                "reutilizada": result.reutilizada,
            },
            status=202,
        )

    @extend_schema(responses=ResultadoCatalogoSerializer)
    def retrieve(self, request, *args, **kwargs):
        return Response(ResultadoCatalogoSerializer(resultado_catalogo(self.get_object())).data)
