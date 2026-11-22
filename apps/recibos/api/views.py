from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import EsVendedor
from apps.core.serializers import UsuarioResumenSerializer, resumen_usuario
from apps.documentos.http import respuesta_documento_html, respuesta_documento_pdf
from apps.documentos.pdf import renderizar_recibo_pdf
from apps.documentos.services import renderizar_recibo
from apps.recibos.models import Recibo
from apps.recibos.services import anular_recibo


class ReciboSerializer(serializers.ModelSerializer):
    moneda_codigo = serializers.CharField(source="pedido.proforma.moneda.codigo", read_only=True)
    tipo_pago_nombre = serializers.CharField(source="tipo_pago.nombre", read_only=True)
    vendedor_resumen = serializers.SerializerMethodField()

    class Meta:
        model = Recibo
        fields = "__all__"
        read_only_fields = [field.name for field in Recibo._meta.fields]

    @extend_schema_field(UsuarioResumenSerializer(allow_null=True))
    def get_vendedor_resumen(self, recibo):
        proforma = getattr(recibo.pedido, "proforma", None)
        return resumen_usuario(getattr(proforma, "vendedor", None))


class ReciboViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Recibo.objects.all()
    serializer_class = ReciboSerializer
    permission_classes = [EsVendedor]

    def get_queryset(self):
        return Recibo.objects.select_related(
            "pedido__proforma__moneda",
            "pedido__proforma__vendedor",
            "tipo_pago",
        ).order_by("-id")

    @extend_schema(
        request=None,
        responses={(200, "text/html"): OpenApiTypes.STR},
    )
    @action(detail=True, methods=["get"])
    def documento(self, request, pk=None):
        recibo = self.get_object()
        return respuesta_documento_html(
            contenido=renderizar_recibo(recibo.id),
            nombre=f"recibo-{recibo.numero}",
        )

    @extend_schema(
        request=None,
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="documento-pdf",
        pagination_class=None,
        filter_backends=[],
    )
    def documento_pdf(self, request, pk=None):
        recibo = self.get_object()
        return respuesta_documento_pdf(
            contenido=renderizar_recibo_pdf(recibo.id, usuario=request.user),
            nombre=f"recibo-{recibo.numero}",
        )

    @extend_schema(
        request=None,
        responses={200: ReciboSerializer},
    )
    @action(detail=True, methods=["post"])
    def anular(self, request, pk=None):
        recibo = anular_recibo(
            recibo_id=self.get_object().id,
            actor=request.user,
        )
        return Response(self.get_serializer(recibo).data)
