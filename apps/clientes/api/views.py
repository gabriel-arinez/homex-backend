from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import filters, status, viewsets
from rest_framework.response import Response

from apps.clientes.api.serializers import ClienteFiltrosListadoSerializer, ClienteSerializer
from apps.clientes.models import Cliente
from apps.clientes.services import actualizar_cliente, crear_cliente, desactivar_cliente
from apps.core.pagination import PaginacionListadosHOMEX
from apps.core.permissions import EsVendedor


@extend_schema_view(list=extend_schema(parameters=[ClienteFiltrosListadoSerializer]))
class ClienteViewSet(viewsets.ModelViewSet):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    permission_classes = [EsVendedor]
    pagination_class = PaginacionListadosHOMEX
    filter_backends = [filters.SearchFilter]
    search_fields = ["nombres", "apellidos", "empresa", "celular"]

    def get_queryset(self):
        queryset = Cliente.objects.order_by("id")
        if not (self.request.user.is_staff or self.request.user.is_superuser):
            queryset = queryset.filter(created_by=self.request.user)

        filtros = ClienteFiltrosListadoSerializer(data=self.request.query_params.dict())
        filtros.is_valid(raise_exception=True)

        if "activo" in filtros.validated_data:
            queryset = queryset.filter(activo=filtros.validated_data["activo"])
        if "tipo_cliente" in filtros.validated_data:
            queryset = queryset.filter(tipo_cliente_id=filtros.validated_data["tipo_cliente"])

        return queryset

    def perform_create(self, serializer):
        cliente = crear_cliente(actor=self.request.user, revision_esperada=self.request.headers.get('If-Match'), **serializer.validated_data)
        serializer.instance = cliente

    def perform_update(self, serializer):
        cliente = actualizar_cliente(
            cliente=self.get_object(), actor=self.request.user, **serializer.validated_data
        )
        serializer.instance = cliente

    def destroy(self, request, *args, **kwargs):
        desactivar_cliente(cliente=self.get_object(), actor=request.user, revision_esperada=request.headers.get('If-Match'))
        return Response(status=status.HTTP_204_NO_CONTENT)
