from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import serializers, viewsets
from rest_framework.decorators import action

from apps.core.permissions import EsVendedor
from apps.core.serializers import UsuarioResumenSerializer, resumen_usuario
from apps.documentos.http import respuesta_documento_html, respuesta_documento_pdf
from apps.documentos.pdf import renderizar_nota_entrega_pdf
from apps.documentos.services import renderizar_nota_entrega
from apps.notas_entrega.models import NotaEntrega
from apps.proformas.api.serializers import (
    ClienteResumenProformaSerializer,
    ValorCatalogoResumenSerializer,
)
from apps.proformas.models import DetalleProforma


class DetalleNotaEntregaSerializer(serializers.ModelSerializer):
    tipo_item_info = ValorCatalogoResumenSerializer(source="tipo_item", read_only=True)
    unidad_info = ValorCatalogoResumenSerializer(source="unidad", read_only=True)
    tipo_mueble_nombre = serializers.SerializerMethodField()

    class Meta:
        model = DetalleProforma
        fields = [
            "id",
            "tipo_item_info",
            "producto",
            "nombre",
            "descripcion",
            "cantidad",
            "unidad_info",
            "tipo_mueble_nombre",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_tipo_mueble_nombre(self, detalle):
        if detalle.tipo_item.codigo != "MUEBLE_MEDIDA":
            return None
        spec = getattr(detalle, "especificacionmueble", None)
        if spec is None or spec.tipo_mueble is None:
            return None
        return spec.tipo_mueble.nombre


class NotaEntregaSerializer(serializers.ModelSerializer):
    proforma_numero = serializers.IntegerField(source="pedido.proforma.numero", read_only=True)
    proforma_titulo = serializers.CharField(
        source="pedido.proforma.titulo", read_only=True, allow_null=True
    )
    cliente_resumen = serializers.SerializerMethodField()
    vendedor_resumen = serializers.SerializerMethodField()
    detalles = DetalleNotaEntregaSerializer(
        source="pedido.proforma.detalles", many=True, read_only=True
    )

    class Meta:
        model = NotaEntrega
        fields = [
            "id",
            "pedido",
            "vendedor",
            "numero",
            "fecha",
            "created_by",
            "updated_by",
            "proforma_numero",
            "proforma_titulo",
            "cliente_resumen",
            "vendedor_resumen",
            "detalles",
        ]
        read_only_fields = fields

    @extend_schema_field(ClienteResumenProformaSerializer(allow_null=True))
    def get_cliente_resumen(self, nota):
        proforma = nota.pedido.proforma
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

    @extend_schema_field(UsuarioResumenSerializer(allow_null=True))
    def get_vendedor_resumen(self, nota):
        proforma = getattr(nota.pedido, "proforma", None)
        return resumen_usuario(
            getattr(nota, "vendedor", None) or getattr(proforma, "vendedor", None)
        )


class NotaEntregaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = NotaEntrega.objects.all()
    serializer_class = NotaEntregaSerializer
    permission_classes = [EsVendedor]

    def get_queryset(self):
        return (
            NotaEntrega.objects.select_related(
                "pedido__proforma__cliente",
                "pedido__proforma__vendedor",
                "vendedor",
            )
            .prefetch_related(
                "pedido__proforma__detalles__tipo_item",
                "pedido__proforma__detalles__unidad",
                "pedido__proforma__detalles__especificacionmueble__tipo_mueble",
            )
            .order_by("-id")
        )

    @extend_schema(
        request=None,
        responses={(200, "text/html"): OpenApiTypes.STR},
    )
    @action(detail=True, methods=["get"])
    def documento(self, request, pk=None):
        nota = self.get_object()
        return respuesta_documento_html(
            contenido=renderizar_nota_entrega(nota.id),
            nombre=f"nota-entrega-{nota.numero}",
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
        nota = self.get_object()
        return respuesta_documento_pdf(
            contenido=renderizar_nota_entrega_pdf(nota.id, usuario=request.user),
            nombre=f"nota-entrega-{nota.numero}",
        )
