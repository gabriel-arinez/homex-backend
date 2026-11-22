from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import EsOperadorOrdenTrabajo, es_jefe_taller
from apps.documentos.http import respuesta_documento_html, respuesta_documento_pdf
from apps.documentos.pdf import renderizar_orden_trabajo_pdf
from apps.documentos.services import renderizar_orden_trabajo
from apps.ordenes_trabajo.models import OrdenTrabajo
from apps.pedidos.services import cambiar_estado_pedido
from apps.proformas.api.serializers import (
    ClienteResumenProformaSerializer,
    EspecificacionMuebleSerializer,
    ValorCatalogoResumenSerializer,
)
from apps.proformas.models import DetalleProforma


class DetalleOrdenTrabajoSerializer(serializers.ModelSerializer):
    tipo_item_info = ValorCatalogoResumenSerializer(source="tipo_item", read_only=True)
    unidad_info = ValorCatalogoResumenSerializer(source="unidad", read_only=True)
    especificacion = serializers.SerializerMethodField()
    descripcion = serializers.CharField(read_only=True, allow_null=True)

    class Meta:
        model = DetalleProforma
        fields = [
            "id",
            "tipo_item_info",
            "producto",
            "familia_producto",
            "nombre",
            "descripcion",
            "cantidad",
            "unidad_info",
            "especificacion",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if (
            instance.tipo_item.codigo != "MUEBLE_MEDIDA"
            or request is None
            or not es_jefe_taller(request.user)
        ):
            data["descripcion"] = None
        return data

    @extend_schema_field(EspecificacionMuebleSerializer(allow_null=True))
    def get_especificacion(self, detalle):
        request = self.context.get("request")
        if request is None or not es_jefe_taller(request.user):
            return None
        if detalle.tipo_item.codigo != "MUEBLE_MEDIDA":
            return None
        especificacion = getattr(detalle, "especificacionmueble", None)
        if especificacion is None:
            return None
        return EspecificacionMuebleSerializer(especificacion).data


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
    proforma_titulo = serializers.CharField(
        source="pedido.proforma.titulo",
        read_only=True,
        allow_null=True,
    )
    pedido_estado_codigo = serializers.CharField(
        source="pedido.estado.codigo",
        read_only=True,
    )
    pedido_estado_nombre = serializers.CharField(
        source="pedido.estado.nombre",
        read_only=True,
    )
    cliente_resumen = serializers.SerializerMethodField()
    detalles = DetalleOrdenTrabajoSerializer(
        source="pedido.proforma.detalles",
        many=True,
        read_only=True,
    )

    class Meta:
        model = OrdenTrabajo
        fields = [
            "id",
            "pedido",
            "pedido_estado_codigo",
            "pedido_estado_nombre",
            "proforma_numero",
            "proforma_titulo",
            "cliente_resumen",
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

    @extend_schema_field(ClienteResumenProformaSerializer(allow_null=True))
    def get_cliente_resumen(self, orden):
        proforma = orden.pedido.proforma
        if proforma.cliente_id is None:
            return None

        cliente = proforma.cliente
        nombre_actual = " ".join(
            value.strip()
            for value in [cliente.nombres or "", cliente.apellidos or ""]
            if value.strip()
        )
        tiene_snapshot = any(
            value is not None
            for value in [
                proforma.cliente_nombre_snapshot,
                proforma.cliente_empresa_snapshot,
                proforma.cliente_celular_snapshot,
            ]
        )

        return {
            "id": proforma.cliente_id,
            "nombre": proforma.cliente_nombre_snapshot if tiene_snapshot else nombre_actual,
            "empresa": proforma.cliente_empresa_snapshot if tiene_snapshot else cliente.empresa,
            "celular": proforma.cliente_celular_snapshot if tiene_snapshot else cliente.celular,
        }


class OrdenTrabajoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = OrdenTrabajo.objects.all()
    serializer_class = OrdenTrabajoSerializer
    permission_classes = [EsOperadorOrdenTrabajo]

    def get_queryset(self):
        queryset = (
            OrdenTrabajo.objects.select_related(
                "pedido__estado",
                "pedido__proforma__cliente",
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
        if (
            self.request.user.is_staff
            or self.request.user.is_superuser
            or es_jefe_taller(self.request.user)
        ):
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
            contenido=renderizar_orden_trabajo(orden.id, actor=request.user),
            nombre=f"orden-trabajo-{orden.numero}",
        )

    @extend_schema(request=None, responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(
        detail=True,
        methods=["get"],
        url_path="documento-pdf",
        pagination_class=None,
        filter_backends=[],
    )
    def documento_pdf(self, request, pk=None):
        orden = self.get_object()
        return respuesta_documento_pdf(
            contenido=renderizar_orden_trabajo_pdf(orden.id, usuario=request.user),
            nombre=f"orden-trabajo-{orden.numero}",
        )

    @extend_schema(request=None, responses={200: OrdenTrabajoSerializer})
    @action(
        detail=True,
        methods=["post"],
        url_path="marcar-listo-entrega",
    )
    def marcar_listo_entrega(self, request, pk=None):
        orden = self.get_object()
        cambiar_estado_pedido(
            pedido_id=orden.pedido_id,
            actor=request.user,
            estado_codigo="LISTO_ENTREGA",
        )
        orden.refresh_from_db()
        return Response(self.get_serializer(orden).data)
