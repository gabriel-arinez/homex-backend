from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import EsVendedor
from apps.documentos.http import respuesta_documento_html
from apps.documentos.services import renderizar_recibo
from apps.recibos.models import Recibo
from apps.recibos.services import anular_recibo


class ReciboSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recibo
        fields = "__all__"
        read_only_fields = [field.name for field in Recibo._meta.fields]


class ReciboViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Recibo.objects.all()
    serializer_class = ReciboSerializer
    permission_classes = [EsVendedor]

    def get_queryset(self):
        queryset = Recibo.objects.select_related(
            "pedido__proforma",
            "tipo_pago",
        ).order_by("-id")

        if self.request.user.is_staff or self.request.user.is_superuser:
            return queryset

        return queryset.filter(pedido__proforma__vendedor=self.request.user)

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
        responses={200: ReciboSerializer},
    )
    @action(detail=True, methods=["post"])
    def anular(self, request, pk=None):
        recibo = anular_recibo(
            recibo_id=self.get_object().id,
            actor=request.user,
        )
        return Response(self.get_serializer(recibo).data)
