from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.capturas.api.serializers import (
    CapturaAceptadaSerializer,
    CapturaRevisionSerializer,
    ConfirmacionHITLRespuestaSerializer,
    ConfirmarCapturaSerializer,
    CrearCapturaMultipartSerializer,
    CrearCapturaSerializer,
    CrearCapturaTextoSerializer,
)
from apps.capturas.audio import AudioTemporalInvalido
from apps.capturas.hitl import confirmar_captura
from apps.capturas.models import Captura
from apps.capturas.services import recibir_captura_audio, recibir_captura_texto
from apps.core.permissions import EsVendedor


class CapturaViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Captura.objects.all()
    permission_classes = [EsVendedor]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    serializer_class = CrearCapturaSerializer

    def get_queryset(self):
        queryset = Captura.objects.select_related("proforma").order_by("-id")
        if self.request.user.is_staff or self.request.user.is_superuser:
            return queryset
        return queryset.filter(vendedor=self.request.user)

    def get_serializer_class(self):
        if self.action == "retrieve":
            return CapturaRevisionSerializer
        if self.action == "confirmar":
            return ConfirmarCapturaSerializer
        return CrearCapturaSerializer

    @extend_schema(
        request={
            "application/json": CrearCapturaTextoSerializer,
            "application/x-www-form-urlencoded": CrearCapturaTextoSerializer,
            "multipart/form-data": CrearCapturaMultipartSerializer,
        },
        responses={
            202: CapturaAceptadaSerializer,
            409: OpenApiResponse(
                description="La clave de idempotencia ya fue utilizada con otra solicitud."
            ),
        },
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        argumentos = {
            "actor": request.user,
            "clave_idempotencia": datos["clave_idempotencia"],
            "proforma_id": datos["proforma"],
            "proforma_detalle_id": datos.get("proforma_detalle"),
        }
        try:
            if "audio" in datos:
                recepcion = recibir_captura_audio(**argumentos, archivo=datos["audio"])
            else:
                recepcion = recibir_captura_texto(**argumentos, texto=datos["texto"])
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

    @extend_schema(
        request=ConfirmarCapturaSerializer,
        responses={
            201: ConfirmacionHITLRespuestaSerializer,
            400: OpenApiResponse(
                description="Payload inválido, captura no procesable o proforma no editable."
            ),
            409: OpenApiResponse(
                description=(
                    "La captura ya tiene una confirmación final o ya está vinculada "
                    "a un detalle comercial."
                )
            ),
            415: OpenApiResponse(description="La confirmación HITL acepta application/json."),
        },
    )
    @action(detail=True, methods=["post"], parser_classes=[JSONParser])
    def confirmar(self, request, pk=None):
        captura = self.get_object()
        serializer = ConfirmarCapturaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resultado = confirmar_captura(
            captura_id=captura.id, actor=request.user, **serializer.validated_data
        )
        return Response(
            {
                "captura_id": resultado.captura.id,
                "detalle_id": resultado.detalle.id,
                "item_humano_id": resultado.item_humano.id,
                "evaluacion_id": resultado.evaluacion.id,
                "proforma_estado": resultado.captura.proforma.estado.codigo,
            },
            status=status.HTTP_201_CREATED,
        )
