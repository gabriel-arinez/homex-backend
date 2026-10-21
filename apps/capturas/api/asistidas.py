from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.capturas.api.serializers import (
    CapturaAceptadaSerializer,
    CrearCapturaSerializer,
    EstrictoSerializer,
)
from apps.capturas.asistidas import MODO, recibir_asistida, resultado_asistida
from apps.capturas.audio import AudioTemporalInvalido
from apps.capturas.models import Captura
from apps.core.permissions import EsVendedor


class CrearAsistidaSerializer(CrearCapturaSerializer, EstrictoSerializer):
    sesion_borrador = serializers.UUIDField()
    proforma = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    moneda_codigo = serializers.ChoiceField(choices=["BOB", "USD"], required=False)
    captura_origen = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    proforma_detalle = None


class ResolucionPendienteSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(
        choices=["DIMENSION", "DIMENSIONES_NUEVAS", "COMPONENTE", "ATRIBUTO_GENERAL"]
    )
    clave = serializers.CharField(required=False)
    uid = serializers.CharField(required=False)
    campo = serializers.CharField(required=False)
    cantidad = serializers.IntegerField(min_value=1, required=False)


class PendienteAsistidaSerializer(serializers.Serializer):
    resolucion = ResolucionPendienteSerializer(required=False, allow_null=True)
    codigo = serializers.CharField()
    ruta = serializers.CharField(allow_blank=True)
    mensaje = serializers.CharField()


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


class MotorAsistidaSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=["RULES_ONLY", "HYBRID"])
    rules_version = serializers.CharField()
    model_version = serializers.CharField(allow_null=True)
    normalization_version = serializers.CharField()


class ResultadoAsistidaSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    estado = serializers.CharField()
    intento_id = serializers.IntegerField(allow_null=True)
    texto_transcrito_original = serializers.CharField(allow_null=True)
    resultado = serializers.ChoiceField(
        choices=["PROCESSING", "REQUIRES_REVIEW", "NO_PROPOSAL", "ERROR"]
    )
    propuesta_configurador = PropuestaConfiguradorSerializer(allow_null=True)
    pendientes = PendienteAsistidaSerializer(many=True)
    version_proyeccion = serializers.CharField()
    motor = MotorAsistidaSerializer(allow_null=True)
    error_codigo = serializers.CharField(allow_null=True)


class CapturaAsistidaViewSet(
    mixins.CreateModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    queryset = Captura.objects.none()
    permission_classes = [EsVendedor]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    serializer_class = CrearAsistidaSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Captura.objects.none()
        queryset = Captura.objects.filter(modo_captura=MODO)
        if self.request.user.is_staff or self.request.user.is_superuser:
            return queryset
        return queryset.filter(vendedor=self.request.user)

    def get_serializer_class(self):
        return ResultadoAsistidaSerializer if self.action == "retrieve" else CrearAsistidaSerializer

    @extend_schema(
        request=CrearAsistidaSerializer,
        responses={
            202: CapturaAceptadaSerializer,
            400: OpenApiResponse(description="Entrada o contexto de borrador inválidos."),
            401: OpenApiResponse(description="Se requiere autenticación."),
            403: OpenApiResponse(description="Sin permiso comercial o de proforma."),
            404: OpenApiResponse(description="Captura de origen o proforma no disponible."),
            409: OpenApiResponse(description="Idempotencia incompatible."),
            415: OpenApiResponse(description="Tipo de contenido no admitido."),
        },
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            recepcion = recibir_asistida(actor=request.user, **serializer.validated_data)
        except AudioTemporalInvalido as exc:
            raise serializers.ValidationError({"audio": str(exc)}) from exc
        return Response(
            {
                "id": recepcion.captura.id,
                "estado": recepcion.captura.estado,
                "intento_id": recepcion.intento.id,
                "numero_intento": recepcion.intento.numero_intento,
                "reutilizada": recepcion.reutilizada,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @extend_schema(responses=ResultadoAsistidaSerializer)
    def retrieve(self, request, *args, **kwargs):
        return Response(ResultadoAsistidaSerializer(resultado_asistida(self.get_object())).data)
