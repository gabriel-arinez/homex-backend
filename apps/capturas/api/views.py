from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.capturas.api.serializers import (
    CapturaAceptadaSerializer,
    CrearCapturaMultipartSerializer,
    CrearCapturaSerializer,
    CrearCapturaTextoSerializer,
)
from apps.capturas.audio import AudioTemporalInvalido
from apps.capturas.services import recibir_captura_audio, recibir_captura_texto
from apps.core.permissions import EsVendedor


class CapturaViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    permission_classes = [EsVendedor]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    serializer_class = CrearCapturaSerializer

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
