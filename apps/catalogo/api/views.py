from django.db.models import DecimalField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.catalogo.api.serializers import (
    AtributoMuebleSerializer,
    CargaImagenSerializer,
    CatalogoAtributosMuebleSerializer,
    CatalogoOpcionesFiltrosSerializer,
    DescuentoProductoSerializer,
    FamiliaProductoSerializer,
    ProductoFiltrosListadoSerializer,
    ProductoPisoSerializer,
    ProductoSerializer,
    ProductoSillaSerializer,
    TipoMuebleConflictoSerializer,
    TipoMuebleCrearSerializer,
    TipoMuebleRespuestaSerializer,
    ValorCatalogoPublicoSerializer,
)
from apps.catalogo.models import (
    DescuentoProducto,
    FamiliaProducto,
    MetadatoAtributoMueble,
    Producto,
    ProductoPiso,
    ProductoSilla,
    ValorCatalogo,
)
from apps.catalogo.services import eliminar_imagen_principal, reemplazar_imagen_principal
from apps.core.exceptions import ConflictoComercial
from apps.core.pagination import PaginacionListadosHOMEX
from apps.core.permissions import EsAdministradorComercial, EsVendedor
from apps.proformas.models import DetalleProforma

REVISION_PRODUCTO = OpenApiParameter(
    name="If-Match",
    type=str,
    location=OpenApiParameter.HEADER,
    required=True,
    description="Revisión del producto devuelta por GET; evita sobrescrituras concurrentes.",
)


@extend_schema_view(
    list=extend_schema(parameters=[ProductoFiltrosListadoSerializer]),
    update=extend_schema(parameters=[REVISION_PRODUCTO]),
    partial_update=extend_schema(parameters=[REVISION_PRODUCTO]),
)
class ProductoViewSet(viewsets.ModelViewSet):
    serializer_class = ProductoSerializer
    pagination_class = PaginacionListadosHOMEX
    filter_backends = [filters.SearchFilter]
    search_fields = ["sku", "nombre"]

    def get_queryset(self):
        demanda = (
            DetalleProforma.objects.filter(
                producto_id=OuterRef("pk"),
                proforma__estado__codigo__in=["EN_REVISION", "ENVIADA"],
            )
            .values("producto_id")
            .annotate(total=Sum("cantidad"))
            .values("total")[:1]
        )
        queryset = (
            Producto.objects.select_related(
                "categoria__concepto",
                "unidad_stock__concepto",
                "familia",
                "productosilla",
                "productopiso",
                "descuentoproducto",
            )
            .annotate(
                demanda_pendiente_calculada=Coalesce(
                    Subquery(demanda, output_field=DecimalField(max_digits=14, decimal_places=4)),
                    Value(0),
                    output_field=DecimalField(max_digits=14, decimal_places=4),
                )
            )
            .order_by("nombre", "id")
        )
        filtros = ProductoFiltrosListadoSerializer(data=self.request.query_params.dict())
        filtros.is_valid(raise_exception=True)

        if "activo" in filtros.validated_data:
            queryset = queryset.filter(activo=filtros.validated_data["activo"])
        if "categoria" in filtros.validated_data:
            queryset = queryset.filter(categoria=filtros.validated_data["categoria"])
        if "familia" in filtros.validated_data:
            queryset = queryset.filter(familia=filtros.validated_data["familia"])

        relaciones = {
            "marca": {"SILLA": "productosilla__marca", "PISO_FLOTANTE": "productopiso__marca"},
            "color_primario": {"SILLA": "productosilla__color_primario"},
            "tipo": {"PISO_FLOTANTE": "productopiso__tipo"},
            "material": {"PISO_FLOTANTE": "productopiso__material"},
            "diseno": {"PISO_FLOTANTE": "productopiso__diseno"},
            "acabado": {"PISO_FLOTANTE": "productopiso__acabado"},
        }
        categoria = filtros.validated_data.get("categoria")
        categoria_codigo = categoria.codigo if categoria else None
        for campo, rutas in relaciones.items():
            if campo in filtros.validated_data:
                queryset = queryset.filter(
                    **{rutas[categoria_codigo]: filtros.validated_data[campo]}
                )
        if "modelo" in filtros.validated_data:
            queryset = queryset.filter(
                productosilla__modelo__icontains=filtros.validated_data["modelo"]
            )
        if "espesor_mm" in filtros.validated_data:
            queryset = queryset.filter(
                productopiso__espesor_mm=filtros.validated_data["espesor_mm"]
            )
        if "unidad_stock" in filtros.validated_data:
            queryset = queryset.filter(unidad_stock=filtros.validated_data["unidad_stock"])

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


class FamiliaProductoViewSet(viewsets.ModelViewSet):
    queryset = FamiliaProducto.objects.order_by("nombre", "id")
    serializer_class = FamiliaProductoSerializer
    pagination_class = PaginacionListadosHOMEX

    def get_permissions(self):
        if self.action in {"list", "retrieve"}:
            return [EsVendedor()]
        return [EsAdministradorComercial()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


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


@extend_schema_view(list=extend_schema(parameters=[CatalogoOpcionesFiltrosSerializer]))
class CatalogoOpcionesViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = ValorCatalogo.objects.none()
    serializer_class = ValorCatalogoPublicoSerializer
    permission_classes = [EsVendedor]
    pagination_class = None

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ValorCatalogo.objects.none()

        filtros = CatalogoOpcionesFiltrosSerializer(data=self.request.query_params.dict())
        filtros.is_valid(raise_exception=True)
        concepto = filtros.validated_data["concepto"]

        return (
            ValorCatalogo.objects.select_related("concepto")
            .filter(
                concepto__codigo=concepto,
                concepto__activo=True,
                activo=True,
            )
            .order_by("nombre", "id")
        )


class AtributosMuebleViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [EsVendedor]
    pagination_class = None

    @extend_schema(
        parameters=[OpenApiParameter("search", str)], responses=CatalogoAtributosMuebleSerializer
    )
    def list(self, request, *args, **kwargs):
        from apps.catalogo.atributos_mueble import MAX_COMPONENTES, MAX_CONJUNTOS, normalizar

        registros = list(
            MetadatoAtributoMueble.objects.select_related("valor")
            .filter(valor__concepto__codigo="ATRIBUTO_MUEBLE", valor__activo=True)
            .order_by("valor__nombre", "valor_id")
        )
        search = normalizar(request.query_params.get("search", ""))
        if search:
            registros = [
                item
                for item in registros
                if search in normalizar(" ".join([item.valor.nombre, *item.sinonimos]))
            ]
        data = {
            "limites": {"max_conjuntos": MAX_CONJUNTOS, "max_componentes": MAX_COMPONENTES},
            "atributos": AtributoMuebleSerializer(registros, many=True).data,
        }
        return Response(data)


class TiposMuebleViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    permission_classes = [EsVendedor]
    serializer_class = TipoMuebleCrearSerializer

    @extend_schema(
        request=TipoMuebleCrearSerializer,
        responses={201: TipoMuebleRespuestaSerializer, 409: TipoMuebleConflictoSerializer},
    )
    def create(self, request, *args, **kwargs):
        from apps.catalogo.atributos_mueble import crear_tipo_mueble, resumen_tipo

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            valor = crear_tipo_mueble(actor=request.user, **serializer.validated_data)
        except ConflictoComercial as exc:
            existente = exc.detail["existente"]
            return Response(
                {
                    "codigo": "tipo_duplicado",
                    "existente": {
                        "id": int(existente["id"]),
                        "codigo": str(existente["codigo"]),
                        "nombre": str(existente["nombre"]),
                    },
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(resumen_tipo(valor), status=status.HTTP_201_CREATED)
