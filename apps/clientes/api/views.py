from rest_framework import viewsets

from apps.clientes.api.serializers import ClienteSerializer
from apps.clientes.models import Cliente
from apps.clientes.services import actualizar_cliente, crear_cliente
from apps.core.permissions import EsVendedor


class ClienteViewSet(viewsets.ModelViewSet):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    permission_classes = [EsVendedor]

    def get_queryset(self):
        queryset = Cliente.objects.order_by("id")
        if self.request.user.is_staff or self.request.user.is_superuser:
            return queryset
        return queryset.filter(created_by=self.request.user)

    def perform_create(self, serializer):
        cliente = crear_cliente(actor=self.request.user, **serializer.validated_data)
        serializer.instance = cliente

    def perform_update(self, serializer):
        cliente = actualizar_cliente(
            cliente=self.get_object(), actor=self.request.user, **serializer.validated_data
        )
        serializer.instance = cliente
