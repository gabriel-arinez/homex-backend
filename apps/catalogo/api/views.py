from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.catalogo.api.serializers import (
    CargaImagenSerializer,
    DescuentoProductoSerializer,
    ProductoFiltrosListadoSerializer,
    ProductoPisoSerializer,
    ProductoSerializer,
    ProductoSillaSerializer,
)
from apps.catalogo.models import DescuentoProducto, Producto, ProductoPiso, ProductoSilla
from apps.catalogo.services import eliminar_imagen_principal, reemplazar_imagen_principal
from apps.core.pagination import PaginacionListadosHOMEX
from apps.core.permissions import EsAdministradorComercial, EsVendedor


@extend_schema_view(list=extend_schema(parameters=[ProductoFiltrosListadoSerializer]))
class ProductoViewSet(viewsets.ModelViewSet):
    serializer_class = ProductoSerializer
    pagination_class = PaginacionListadosHOMEX
    filter_backends = [filters.SearchFilter]
    search_fields = ["sku", "nombre"]

    def get_queryset(self):
        queryset = Producto.objects.order_by("nombre", "id")
        filtros = ProductoFiltrosListadoSerializer(data=self.request.query_params)
        filtros.is_valid(raise_exception=True)

        if "activo" in filtros.validated_data:
            queryset = queryset.filter(activo=filtros.validated_data["activo"])
        if "categoria" in filtros.validated_data:
            queryset = queryset.filter(categoria_id=filtros.validated_data["categoria"])

        return queryset

    def get_permissions(self):
        if self.action in {"list", "retrieve"}:
            return [EsVendedor()]
        return [EsAdministradorComercial()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @extend_schema(request=CargaImagenSerializer, responses={201: ProductoSerializer})
    @action(detail=True, methods=["post"], url_path="imagen-principal")
    def imagen_principal(self, request, pk=None):
        archivo = request.FILES.get("archivo")
        if archivo is None:
            return Response({"archivo": ["Debe enviar un archivo multipart."]}, status=400)
        producto = reemplazar_imagen_principal(
            producto=self.get_object(), archivo=archivo, actor=request.user
        )
        return Response(self.get_serializer(producto).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={204: None})
    @imagen_principal.mapping.delete
    def eliminar_imagen_principal(self, request, pk=None):
        eliminar_imagen_principal(producto=self.get_object(), actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class _FichaProductoViewSet(viewsets.ModelViewSet):
    permission_classes = [EsAdministradorComercial]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class ProductoSillaViewSet(_FichaProductoViewSet):
    queryset = ProductoSilla.objects.order_by("producto_id")
    serializer_class = ProductoSillaSerializer


class ProductoPisoViewSet(_FichaProductoViewSet):
    queryset = ProductoPiso.objects.order_by("producto_id")
    serializer_class = ProductoPisoSerializer


class DescuentoProductoViewSet(_FichaProductoViewSet):
    queryset = DescuentoProducto.objects.order_by("producto_id")
    serializer_class = DescuentoProductoSerializer
