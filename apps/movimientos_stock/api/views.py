from django.db.models import Q
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers, viewsets

from apps.catalogo.models import Producto, ValorCatalogo
from apps.core.pagination import PaginacionListadosHOMEX
from apps.core.permissions import EsVendedor
from apps.movimientos_stock.models import MovimientoStock


class ValorCatalogoMovimientoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ValorCatalogo
        fields = ["id", "codigo", "nombre"]
        read_only_fields = fields


class ProductoResumenMovimientoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Producto
        fields = ["id", "sku", "nombre"]
        read_only_fields = fields


class MovimientoStockFiltrosSerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=False)
    producto = serializers.IntegerField(required=False, min_value=1)
    pedido = serializers.IntegerField(required=False, min_value=1)
    tipo_movimiento = serializers.CharField(required=False, max_length=80)
    fecha_desde = serializers.DateField(required=False)
    fecha_hasta = serializers.DateField(required=False)

    def validate(self, attrs):
        desde = attrs.get("fecha_desde")
        hasta = attrs.get("fecha_hasta")
        if desde and hasta and desde > hasta:
            raise serializers.ValidationError(
                {"fecha_hasta": "Debe ser igual o posterior a fecha_desde."}
            )
        return attrs


class MovimientoStockSerializer(serializers.ModelSerializer):
    producto_resumen = ProductoResumenMovimientoSerializer(source="producto", read_only=True)
    tipo_movimiento_info = ValorCatalogoMovimientoSerializer(
        source="tipo_movimiento",
        read_only=True,
    )

    class Meta:
        model = MovimientoStock
        fields = [
            "id",
            "fecha",
            "tipo_movimiento",
            "tipo_movimiento_info",
            "cantidad",
            "producto",
            "producto_resumen",
            "pedido",
            "movimiento_referencia",
            "observaciones",
            "created_by",
        ]
        read_only_fields = fields


@extend_schema_view(
    list=extend_schema(parameters=[MovimientoStockFiltrosSerializer]),
)
class MovimientoStockViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MovimientoStockSerializer
    permission_classes = [EsVendedor]
    pagination_class = PaginacionListadosHOMEX
    queryset = MovimientoStock.objects.all()

    def get_queryset(self):
        queryset = MovimientoStock.objects.select_related(
            "producto",
            "tipo_movimiento",
            "pedido",
        ).order_by("-fecha", "-id")

        if self.action != "list":
            return queryset

        filtros = MovimientoStockFiltrosSerializer(data=self.request.query_params.dict())
        filtros.is_valid(raise_exception=True)
        datos = filtros.validated_data

        if "search" in datos:
            termino = datos["search"].strip()
            queryset = queryset.filter(
                Q(producto__sku__icontains=termino)
                | Q(producto__nombre__icontains=termino)
                | Q(observaciones__icontains=termino)
            )
        if "producto" in datos:
            queryset = queryset.filter(producto_id=datos["producto"])
        if "pedido" in datos:
            queryset = queryset.filter(pedido_id=datos["pedido"])
        if "tipo_movimiento" in datos:
            queryset = queryset.filter(
                tipo_movimiento__codigo__iexact=datos["tipo_movimiento"]
            )
        if "fecha_desde" in datos:
            queryset = queryset.filter(fecha__date__gte=datos["fecha_desde"])
        if "fecha_hasta" in datos:
            queryset = queryset.filter(fecha__date__lte=datos["fecha_hasta"])

        return queryset
