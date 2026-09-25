from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.core.pagination import PaginacionListadosHOMEX
from apps.core.permissions import EsVendedor
from apps.documentos.models import ArchivoAdjunto
from apps.documentos.services import adjuntar_imagen, adjunto_publico, eliminar_adjunto
from apps.pedidos.services import aprobar_proforma
from apps.proformas.api.serializers import (
    AprobarProformaRespuestaSerializer,
    ArchivoAdjuntoSerializer,
    CargaArchivoImagenSerializer,
    CrearProformaSerializer,
    DetalleProformaSerializer,
    EspecificacionMuebleSerializer,
    ProformaFiltrosListadoSerializer,
    ProformaListadoSerializer,
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

CONFLICTO_COMERCIAL = OpenApiResponse(
    description="Conflicto con el estado actual o con una regla comercial concurrente."
)


@extend_schema_view(
    list=extend_schema(parameters=[ProformaFiltrosListadoSerializer]),
    create=extend_schema(
        request=CrearProformaSerializer,
        responses={201: ProformaSerializer},
    ),
)
class ProformaViewSet(viewsets.ModelViewSet):
    queryset = Proforma.objects.all()
    permission_classes = [EsVendedor]
    pagination_class = PaginacionListadosHOMEX
    filter_backends = [filters.SearchFilter]
    search_fields = [
        "=numero",
        "titulo",
        "cliente__nombres",
        "cliente__apellidos",
        "cliente__empresa",
        "cliente__celular",
        "cliente_nombre_snapshot",
        "cliente_empresa_snapshot",
        "cliente_celular_snapshot",
    ]

    def get_queryset(self):
        queryset = Proforma.objects.select_related(
            "cliente",
            "estado",
            "moneda",
            "vendedor",
        ).order_by("-id")

        if self.action != "list":
            queryset = queryset.prefetch_related(
                "detalles__tipo_item",
                "detalles__unidad",
                "detalles__producto",
                "detalles__especificacionmueble__tipo_mueble",
            )

        if not (self.request.user.is_staff or self.request.user.is_superuser):
            queryset = queryset.filter(vendedor=self.request.user)

        if self.action == "list":
            filtros = ProformaFiltrosListadoSerializer(data=self.request.query_params.dict())
            filtros.is_valid(raise_exception=True)
            datos = filtros.validated_data

            if "estado" in datos:
                queryset = queryset.filter(estado__codigo__iexact=datos["estado"])
            if "moneda" in datos:
                queryset = queryset.filter(moneda__codigo__iexact=datos["moneda"])
            if "cliente" in datos:
                queryset = queryset.filter(cliente_id=datos["cliente"])
            if "fecha_desde" in datos:
                queryset = queryset.filter(fecha__gte=datos["fecha_desde"])
            if "fecha_hasta" in datos:
                queryset = queryset.filter(fecha__lte=datos["fecha_hasta"])

        return queryset

    def get_serializer_class(self):
        if self.action == "create":
            return CrearProformaSerializer
        if self.action == "list":
            return ProformaListadoSerializer
        return ProformaSerializer

    def _get_proforma_media(self, pk):
        proforma = get_object_or_404(
            Proforma.objects.select_related("estado").prefetch_related("detalles"),
            pk=pk,
        )
        if (
            proforma.vendedor_id != self.request.user.id
            and not self.request.user.is_staff
            and not self.request.user.is_superuser
        ):
            raise PermissionDenied("No puede operar archivos de una proforma de otro vendedor.")
        return proforma

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        moneda_codigo = datos.pop("moneda_codigo")
        proforma = crear_proforma(actor=request.user, moneda_codigo=moneda_codigo, **datos)
        proforma = self.get_queryset().get(pk=proforma.pk)
        return Response(ProformaSerializer(proforma).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        proforma = actualizar_proforma(
            proforma_id=self.get_object().id,
            actor=self.request.user,
            **serializer.validated_data,
        )
        serializer.instance = proforma

    def destroy(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @extend_schema(
        request=None,
        responses={
            200: AprobarProformaRespuestaSerializer,
            409: CONFLICTO_COMERCIAL,
        },
    )
    @action(detail=True, methods=["post"])
    def aprobar(self, request, pk=None):
        pedido = aprobar_proforma(
            proforma_id=self.get_object().id,
            actor=request.user,
        )
        return Response(
            {
                "pedido_id": pedido.id,
                "estado": pedido.estado.codigo,
            }
        )

    @extend_schema(
        request=None,
        responses={
            200: ProformaSerializer,
            409: CONFLICTO_COMERCIAL,
        },
    )
    @action(detail=True, methods=["post"])
    def enviar(self, request, pk=None):
        proforma = enviar_proforma(proforma_id=self.get_object().id, actor=request.user)
        proforma = self.get_queryset().get(pk=proforma.pk)
        return Response(ProformaSerializer(proforma).data)

    @extend_schema(
        parameters=[OpenApiParameter("detalle_id", OpenApiTypes.INT, OpenApiParameter.PATH)],
        request=CargaArchivoImagenSerializer,
        responses={
            200: ArchivoAdjuntoSerializer(many=True),
            201: ArchivoAdjuntoSerializer,
            409: CONFLICTO_COMERCIAL,
        },
    )
    @action(
        detail=True,
        methods=["get", "post"],
        url_path=r"detalles/(?P<detalle_id>[^/.]+)/archivos",
    )
    def archivos(self, request, pk=None, detalle_id=None):
        proforma = self._get_proforma_media(pk)
        if request.method == "GET":
            archivos = ArchivoAdjunto.objects.filter(
                proforma=proforma,
                proforma_detalle_id=detalle_id,
            )
            return Response([adjunto_publico(archivo) for archivo in archivos])

        archivo = request.FILES.get("archivo")
        if archivo is None:
            return Response({"archivo": ["Debe enviar un archivo multipart."]}, status=400)
        adjunto = adjuntar_imagen(
            proforma_id=proforma.id,
            detalle_id=detalle_id,
            archivo=archivo,
            actor=request.user,
        )
        return Response(adjunto_publico(adjunto), status=status.HTTP_201_CREATED)

    @extend_schema(
        parameters=[
            OpenApiParameter("detalle_id", OpenApiTypes.INT, OpenApiParameter.PATH),
            OpenApiParameter("archivo_id", OpenApiTypes.INT, OpenApiParameter.PATH),
        ],
        request=None,
        responses={
            204: None,
            409: CONFLICTO_COMERCIAL,
        },
    )
    @action(
        detail=True,
        methods=["delete"],
        url_path=r"detalles/(?P<detalle_id>[^/.]+)/archivos/(?P<archivo_id>[^/.]+)",
    )
    def eliminar_archivo(self, request, pk=None, detalle_id=None, archivo_id=None):
        eliminar_adjunto(
            proforma_id=self._get_proforma_media(pk).id,
            detalle_id=detalle_id,
            archivo_id=archivo_id,
            actor=request.user,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        request=DetalleProformaSerializer,
        responses={
            201: DetalleProformaSerializer,
            409: CONFLICTO_COMERCIAL,
        },
    )
    @action(detail=True, methods=["post"], url_path="detalles")
    def agregar_detalle(self, request, pk=None):
        serializer = DetalleProformaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        detalle = agregar_detalle(
            proforma_id=self.get_object().id,
            actor=request.user,
            **serializer.validated_data,
        )
        return Response(DetalleProformaSerializer(detalle).data, status=status.HTTP_201_CREATED)


class DetalleProformaViewSet(viewsets.GenericViewSet):
    queryset = DetalleProforma.objects.all()
    serializer_class = DetalleProformaSerializer
    permission_classes = [EsVendedor]

    def get_queryset(self):
        queryset = DetalleProforma.objects.select_related(
            "proforma",
            "proforma__estado",
            "tipo_item",
            "unidad",
            "especificacionmueble__tipo_mueble",
        )
        if self.request.user.is_staff or self.request.user.is_superuser:
            return queryset
        return queryset.filter(proforma__vendedor=self.request.user)

    @extend_schema(
        request=DetalleProformaSerializer,
        responses={
            200: DetalleProformaSerializer,
            409: CONFLICTO_COMERCIAL,
        },
    )
    def partial_update(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        detalle = actualizar_detalle(
            detalle_id=self.get_object().id,
            actor=request.user,
            **serializer.validated_data,
        )
        return Response(self.get_serializer(detalle).data)

    @extend_schema(
        request=EspecificacionMuebleSerializer,
        responses={
            201: EspecificacionMuebleSerializer,
            409: CONFLICTO_COMERCIAL,
        },
    )
    @action(detail=True, methods=["post"], url_path="especificacion")
    def especificacion(self, request, pk=None):
        serializer = EspecificacionMuebleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        especificacion = crear_especificacion(
            detalle_id=self.get_object().id,
            actor=request.user,
            **serializer.validated_data,
        )
        return Response(
            EspecificacionMuebleSerializer(especificacion).data,
            status=status.HTTP_201_CREATED,
        )
