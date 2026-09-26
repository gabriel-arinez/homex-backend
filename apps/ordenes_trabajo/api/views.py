from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, viewsets
from rest_framework.decorators import action

from apps.core.permissions import EsVendedor
from apps.documentos.http import respuesta_documento_html
from apps.documentos.services import renderizar_orden_trabajo
from apps.ordenes_trabajo.models import OrdenTrabajo
from apps.proformas.api.serializers import (
    DetalleProformaSerializer,
    ValorCatalogoResumenSerializer,
)


class OrdenTrabajoSerializer(serializers.ModelSerializer):
    estado_info = ValorCatalogoResumenSerializer(source="estado", read_only=True)
    estado_saldo_info = ValorCatalogoResumenSerializer(
        source="estado_saldo",
        read_only=True,
        allow_null=True,
    )
    proforma_numero = serializers.IntegerField(
        source="pedido.proforma.numero",
        read_only=True,
    )
    detalles = DetalleProformaSerializer(
        source="pedido.proforma.detalles",
        many=True,
        read_only=True,
    )

    class Meta:
        model = OrdenTrabajo
        fields = [
            "id",
            "pedido",
            "proforma_numero",
            "jefe_taller",
            "numero",
            "fecha",
            "fecha_inicio",
            "fecha_fin",
            "responsable_recepcion",
            "fecha_entrega",
            "lugar_entrega",
            "estado_saldo",
            "estado_saldo_info",
            "estado",
            "estado_info",
            "created_by",
            "updated_by",
            "detalles",
        ]
        read_only_fields = fields


class OrdenTrabajoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = OrdenTrabajo.objects.all()
    serializer_class = OrdenTrabajoSerializer
    permission_classes = [EsVendedor]

    def get_queryset(self):
        queryset = (
            OrdenTrabajo.objects.select_related(
                "pedido__proforma",
                "estado",
                "estado_saldo",
            )
            .prefetch_related(
                "pedido__proforma__detalles__tipo_item",
                "pedido__proforma__detalles__unidad",
                "pedido__proforma__detalles__producto",
                "pedido__proforma__detalles__especificacionmueble__tipo_mueble",
            )
            .order_by("-id")
        )
        if self.request.user.is_staff or self.request.user.is_superuser:
            return queryset
        return queryset.filter(pedido__proforma__vendedor=self.request.user)

    @extend_schema(
        request=None,
        responses={(200, "text/html"): OpenApiTypes.STR},
    )
    @action(detail=True, methods=["get"])
    def documento(self, request, pk=None):
        orden = self.get_object()
        return respuesta_documento_html(
            contenido=renderizar_orden_trabajo(orden.id),
            nombre=f"orden-trabajo-{orden.numero}",
        )
