from rest_framework import serializers, viewsets

from apps.core.permissions import EsVendedor
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
