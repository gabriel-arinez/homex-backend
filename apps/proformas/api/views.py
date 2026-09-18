from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import EsVendedor
from apps.pedidos.services import aprobar_proforma
from apps.proformas.api.serializers import (
    CrearProformaSerializer,
    DetalleProformaSerializer,
    EspecificacionMuebleSerializer,
    ProformaSerializer,
)
from apps.proformas.models import DetalleProforma, Proforma
from apps.proformas.services import (
    actualizar_detalle,
    actualizar_proforma,
    agregar_detalle,
    crear_especificacion,
    crear_proforma,
    enviar_proforma,
)


class ProformaViewSet(viewsets.ModelViewSet):
    queryset = Proforma.objects.all()
    permission_classes = [EsVendedor]

    def get_queryset(self):
        queryset = Proforma.objects.prefetch_related("detalles").order_by("-id")
        if self.request.user.is_staff or self.request.user.is_superuser:
            return queryset
        return queryset.filter(vendedor=self.request.user)

    def get_serializer_class(self):
        return CrearProformaSerializer if self.action == "create" else ProformaSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        moneda_codigo = datos.pop("moneda_codigo")
        proforma = crear_proforma(actor=request.user, moneda_codigo=moneda_codigo, **datos)
        return Response(ProformaSerializer(proforma).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        proforma = actualizar_proforma(
            proforma_id=self.get_object().id, actor=self.request.user, **serializer.validated_data
        )
        serializer.instance = proforma

    def destroy(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(detail=True, methods=["post"])
    def aprobar(self, request, pk=None):
        pedido = aprobar_proforma(proforma_id=self.get_object().id, actor=request.user)
        return Response({"pedido_id": pedido.id, "estado": pedido.estado.codigo})

    @action(detail=True, methods=["post"])
    def enviar(self, request, pk=None):
        proforma = enviar_proforma(proforma_id=self.get_object().id, actor=request.user)
        return Response(ProformaSerializer(proforma).data)

    @action(detail=True, methods=["post"], url_path="detalles")
    def agregar_detalle(self, request, pk=None):
        serializer = DetalleProformaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        detalle = agregar_detalle(
            proforma_id=self.get_object().id, actor=request.user, **serializer.validated_data
        )
        return Response(DetalleProformaSerializer(detalle).data, status=status.HTTP_201_CREATED)


class DetalleProformaViewSet(viewsets.GenericViewSet):
    queryset = DetalleProforma.objects.all()
    serializer_class = DetalleProformaSerializer
    permission_classes = [EsVendedor]

    def get_queryset(self):
        queryset = DetalleProforma.objects.select_related("proforma")
        if self.request.user.is_staff or self.request.user.is_superuser:
            return queryset
        return queryset.filter(proforma__vendedor=self.request.user)

    def partial_update(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        detalle = actualizar_detalle(
            detalle_id=self.get_object().id, actor=request.user, **serializer.validated_data
        )
        return Response(self.get_serializer(detalle).data)

    @action(detail=True, methods=["post"], url_path="especificacion")
    def especificacion(self, request, pk=None):
        serializer = EspecificacionMuebleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        especificacion = crear_especificacion(
            detalle_id=self.get_object().id, actor=request.user, **serializer.validated_data
        )
        return Response(
            EspecificacionMuebleSerializer(especificacion).data, status=status.HTTP_201_CREATED
        )
