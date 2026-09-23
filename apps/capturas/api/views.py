from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response

from apps.capturas.api.serializers import CapturaAceptadaSerializer, CrearCapturaSerializer
from apps.capturas.services import recibir_captura_texto
from apps.core.permissions import EsVendedor


class CapturaViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    permission_classes = [EsVendedor]
    serializer_class = CrearCapturaSerializer

    @extend_schema(
        request=CrearCapturaSerializer,
        responses={202: CapturaAceptadaSerializer},
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        recepcion = recibir_captura_texto(
            actor=request.user,
            clave_idempotencia=datos["clave_idempotencia"],
            proforma_id=datos["proforma"],
            proforma_detalle_id=datos.get("proforma_detalle"),
            texto=datos["texto"],
        )
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
