from django.db.models import Q
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.catalogo.models import Producto, ValorCatalogo
from apps.core.pagination import PaginacionListadosHOMEX
from apps.core.permissions import EsAdministradorComercial, EsVendedor
from apps.movimientos_stock.models import MovimientoStock
from apps.movimientos_stock.services import (
    TODOS_LOS_MOTIVOS,
    calcular_saldos_y_resumen,
    catalogo_motivos_ajuste,
    generar_csv_movimientos,
    label_motivo,
    registrar_ajuste_stock,
)


class ValorCatalogoMovimientoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ValorCatalogo
        fields = ["id", "codigo", "nombre"]
        read_only_fields = fields


class ProductoResumenMovimientoSerializer(serializers.ModelSerializer):
    unidad_stock_info = ValorCatalogoMovimientoSerializer(source="unidad_stock", read_only=True)

    class Meta:
        model = Producto
        fields = ["id", "sku", "nombre", "unidad_stock_info"]
        read_only_fields = fields


class UsuarioResumenMovimientoSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    display_name = serializers.SerializerMethodField()

    def get_display_name(self, usuario) -> str:
        return usuario.get_full_name().strip() or usuario.get_username()


class MovimientoStockFiltrosSerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=False)
    producto = serializers.IntegerField(required=False, min_value=1)
    pedido = serializers.IntegerField(required=False, min_value=1)
    tipo_movimiento = serializers.CharField(required=False, max_length=80)
    direccion = serializers.ChoiceField(choices=["ENTRADA", "SALIDA"], required=False)
    motivo = serializers.ChoiceField(choices=list(TODOS_LOS_MOTIVOS.keys()), required=False)
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
    motivo_label = serializers.SerializerMethodField()
    pedido_relacionado = serializers.SerializerMethodField()
    responsable = UsuarioResumenMovimientoSerializer(
        source="created_by",
        read_only=True,
        allow_null=True,
    )

    def get_motivo_label(self, movimiento) -> str | None:
        return label_motivo(movimiento.motivo)

    def get_pedido_relacionado(self, movimiento) -> int | None:
        if movimiento.pedido_id is not None:
            return movimiento.pedido_id
        # Sólo una REVERSA_VENTA hereda el pedido de su venta original.
        # AJUSTE puede referenciar una venta como evidencia sin ser parte del pedido.
        if movimiento.tipo_movimiento.codigo != "REVERSA_VENTA":
            return None
        referencia = movimiento.movimiento_referencia
        return referencia.pedido_id if referencia is not None else None

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
            "pedido_relacionado",
            "movimiento_referencia",
            "motivo",
            "motivo_label",
            "observaciones",
            "created_by",
            "responsable",
        ]
        read_only_fields = fields


class AjusteStockCrearSerializer(serializers.Serializer):
    producto = serializers.IntegerField(min_value=1)
    tipo_operacion = serializers.ChoiceField(choices=["ENTRADA", "SALIDA"])
    cantidad = serializers.DecimalField(max_digits=14, decimal_places=4)
    motivo = serializers.ChoiceField(choices=list(TODOS_LOS_MOTIVOS.keys()))
    observaciones = serializers.CharField(required=False, allow_blank=True, default="")
    clave_idempotencia = serializers.UUIDField(required=False, allow_null=True)


class MovimientoReporteItemSerializer(MovimientoStockSerializer):
    saldo_anterior = serializers.CharField(allow_null=True, read_only=True)
    saldo_posterior = serializers.CharField(allow_null=True, read_only=True)

    class Meta(MovimientoStockSerializer.Meta):
        fields = [
            *MovimientoStockSerializer.Meta.fields,
            "saldo_anterior",
            "saldo_posterior",
        ]
        read_only_fields = fields


class ReporteResumenSerializer(serializers.Serializer):
    producto_id = serializers.IntegerField()
    unidad_codigo = serializers.CharField()
    unidad_nombre = serializers.CharField()
    stock_actual = serializers.CharField()
    total_entradas = serializers.CharField()
    total_salidas = serializers.CharField()
    variacion_neta = serializers.CharField()
    saldo_inicial_periodo = serializers.CharField(allow_null=True)
    saldo_final_periodo = serializers.CharField(allow_null=True)
    cantidad_movimientos = serializers.IntegerField()


class ReporteMovimientosRespuestaSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    saldo_reconstruible = serializers.BooleanField()
    limitacion_saldo = serializers.CharField(allow_null=True)
    resumen = ReporteResumenSerializer(allow_null=True)
    results = MovimientoReporteItemSerializer(many=True)


class MotivoAjusteItemSerializer(serializers.Serializer):
    codigo = serializers.CharField()
    nombre = serializers.CharField()
    requiere_observaciones = serializers.BooleanField()


class CatalogoMotivosAjusteSerializer(serializers.Serializer):
    ENTRADA = MotivoAjusteItemSerializer(many=True)
    SALIDA = MotivoAjusteItemSerializer(many=True)


@extend_schema_view(
    list=extend_schema(parameters=[MovimientoStockFiltrosSerializer]),
)
class MovimientoStockViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MovimientoStockSerializer
    permission_classes = [EsVendedor]
    pagination_class = PaginacionListadosHOMEX
    queryset = MovimientoStock.objects.all()

    def _base_queryset(self):
        return MovimientoStock.objects.select_related(
            "producto",
            "producto__unidad_stock",
            "tipo_movimiento",
            "pedido",
            "movimiento_referencia__pedido",
            "created_by",
        ).order_by("-fecha", "-id")

    def _filtrar_queryset(self, queryset):
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
            queryset = queryset.filter(
                Q(pedido_id=datos["pedido"])
                | Q(
                    tipo_movimiento__codigo="REVERSA_VENTA",
                    movimiento_referencia__pedido_id=datos["pedido"],
                )
            )
        if "tipo_movimiento" in datos:
            queryset = queryset.filter(tipo_movimiento__codigo__iexact=datos["tipo_movimiento"])
        if "direccion" in datos:
            if datos["direccion"] == "ENTRADA":
                queryset = queryset.filter(cantidad__gt=0)
            else:
                queryset = queryset.filter(cantidad__lt=0)
        if "motivo" in datos:
            queryset = queryset.filter(motivo=datos["motivo"])
        if "fecha_desde" in datos:
            queryset = queryset.filter(fecha__date__gte=datos["fecha_desde"])
        if "fecha_hasta" in datos:
            queryset = queryset.filter(fecha__date__lte=datos["fecha_hasta"])

        return queryset, datos

    def get_queryset(self):
        queryset = self._base_queryset()
        if self.action != "list":
            return queryset
        queryset, _ = self._filtrar_queryset(queryset)
        return queryset

    @extend_schema(
        request=AjusteStockCrearSerializer,
        responses={200: MovimientoStockSerializer, 201: MovimientoStockSerializer},
        parameters=[
            OpenApiParameter(
                name="Idempotency-Key",
                location=OpenApiParameter.HEADER,
                required=False,
                type=str,
            )
        ],
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="ajustes",
        permission_classes=[EsAdministradorComercial],
    )
    def ajustes(self, request):
        serializer = AjusteStockCrearSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        clave = datos.get("clave_idempotencia") or request.headers.get("Idempotency-Key")
        movimiento, replay = registrar_ajuste_stock(
            producto_id=datos["producto"],
            tipo_operacion=datos["tipo_operacion"],
            cantidad=datos["cantidad"],
            motivo=datos["motivo"],
            observaciones=datos.get("observaciones"),
            actor=request.user,
            clave_idempotencia=clave,
        )
        return Response(
            MovimientoStockSerializer(movimiento).data,
            status=status.HTTP_200_OK if replay else status.HTTP_201_CREATED,
        )

    @extend_schema(responses={200: CatalogoMotivosAjusteSerializer})
    @action(
        detail=False,
        methods=["get"],
        url_path="motivos-ajuste",
        permission_classes=[EsVendedor],
    )
    def motivos_ajuste(self, request):
        return Response(catalogo_motivos_ajuste(), status=status.HTTP_200_OK)

    @extend_schema(
        parameters=[MovimientoStockFiltrosSerializer],
        responses={200: ReporteMovimientosRespuestaSerializer},
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="reporte",
        permission_classes=[EsVendedor],
    )
    def reporte(self, request):
        queryset, datos = self._filtrar_queryset(self._base_queryset())
        calculo = calcular_saldos_y_resumen(
            queryset,
            producto_id=datos.get("producto"),
            fecha_desde=datos.get("fecha_desde"),
            fecha_hasta=datos.get("fecha_hasta"),
        )
        pagina = self.paginate_queryset(queryset)
        items = pagina if pagina is not None else list(queryset)
        serializados = MovimientoStockSerializer(items, many=True).data
        saldos_por_id = calculo["saldos_por_id"]
        for item in serializados:
            saldos = saldos_por_id.get(item["id"])
            item["saldo_anterior"] = saldos["saldo_anterior"] if saldos else None
            item["saldo_posterior"] = saldos["saldo_posterior"] if saldos else None

        if pagina is not None:
            paginada = self.get_paginated_response(serializados)
            paginada.data["saldo_reconstruible"] = calculo["saldo_reconstruible"]
            paginada.data["limitacion_saldo"] = calculo["limitacion_saldo"]
            paginada.data["resumen"] = calculo["resumen"]
            return paginada

        return Response(
            {
                "count": len(serializados),
                "next": None,
                "previous": None,
                "saldo_reconstruible": calculo["saldo_reconstruible"],
                "limitacion_saldo": calculo["limitacion_saldo"],
                "resumen": calculo["resumen"],
                "results": serializados,
            }
        )

    @extend_schema(
        parameters=[MovimientoStockFiltrosSerializer],
        responses={200: bytes},
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="exportar-csv",
        permission_classes=[EsVendedor],
    )
    def exportar_csv(self, request):
        queryset, datos = self._filtrar_queryset(self._base_queryset())
        calculo = calcular_saldos_y_resumen(
            queryset,
            producto_id=datos.get("producto"),
            fecha_desde=datos.get("fecha_desde"),
            fecha_hasta=datos.get("fecha_hasta"),
        )
        contenido = generar_csv_movimientos(
            queryset.iterator(chunk_size=500),
            saldos_por_id=calculo["saldos_por_id"],
        )
        response = HttpResponse(contenido, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="movimientos-stock.csv"'
        return response
