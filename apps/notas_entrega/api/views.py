from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, viewsets
from rest_framework.decorators import action

from apps.core.permissions import EsVendedor
from apps.documentos.http import respuesta_documento_html
from apps.documentos.services import renderizar_nota_entrega
from apps.notas_entrega.models import NotaEntrega


class NotaEntregaSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotaEntrega
        fields = "__all__"
        read_only_fields = [field.name for field in NotaEntrega._meta.fields]


class NotaEntregaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = NotaEntrega.objects.all()
    serializer_class = NotaEntregaSerializer
    permission_classes = [EsVendedor]

    def get_queryset(self):
        queryset = NotaEntrega.objects.select_related(
            "pedido__proforma",
            "vendedor",
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
        nota = self.get_object()
        return respuesta_documento_html(
            contenido=renderizar_nota_entrega(nota.id),
            nombre=f"nota-entrega-{nota.numero}",
        )
