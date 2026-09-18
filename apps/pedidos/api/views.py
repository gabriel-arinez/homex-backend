from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import EsVendedor
from apps.pedidos.models import Pedido
from apps.pedidos.services import cancelar_pedido


class PedidoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pedido
        fields = "__all__"
        read_only_fields = tuple(fields)


class PedidoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Pedido.objects.all()
    serializer_class = PedidoSerializer
    permission_classes = [EsVendedor]

    def get_queryset(self):
        queryset = Pedido.objects.select_related("proforma", "estado").order_by("-id")
        if self.request.user.is_staff or self.request.user.is_superuser:
            return queryset
        return queryset.filter(proforma__vendedor=self.request.user)

    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        pedido = cancelar_pedido(pedido_id=self.get_object().id, actor=request.user)
        return Response(self.get_serializer(pedido).data)
