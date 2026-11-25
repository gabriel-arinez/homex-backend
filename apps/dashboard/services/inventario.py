from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, F, Q, Sum, Value
from django.db.models.functions import Coalesce

from apps.catalogo.models import Producto
from apps.dashboard.filters import DashboardFilterParams
from apps.dashboard.services.common import (
    CERO,
    fin_dia_la_paz,
    inicio_dia_la_paz,
    paginar_lista,
    redondear_decimal,
)
from apps.movimientos_stock.models import MovimientoStock
from apps.proformas.models import DetalleProforma


def _filtrar_productos(filtros: DashboardFilterParams):
    qs = Producto.objects.filter(activo=True).select_related("categoria", "unidad_stock")
    if filtros.categoria:
        qs = qs.filter(categoria__codigo=filtros.categoria)
    return qs


def obtener_inventario_admin(filtros: DashboardFilterParams) -> dict:
    qs_prod = _filtrar_productos(filtros)

    por_categoria = [
        {
            "categoria_codigo": r["categoria__codigo"],
            "categoria_nombre": r["categoria__nombre"],
            "total_activos": r["total_activos"],
            "con_stock": r["con_stock"],
            "bajo_pedido": r["bajo_pedido"],
            "stock_bajo": r["stock_bajo"],
            "agotados": r["agotados"],
        }
        for r in qs_prod.values("categoria__codigo", "categoria__nombre")
        .annotate(
            total_activos=Count("id"),
            con_stock=Count("id", filter=Q(modalidad_abastecimiento=Producto.MODALIDAD_CON_STOCK)),
            bajo_pedido=Count(
                "id", filter=Q(modalidad_abastecimiento=Producto.MODALIDAD_BAJO_PEDIDO)
            ),
            stock_bajo=Count(
                "id",
                filter=Q(
                    modalidad_abastecimiento=Producto.MODALIDAD_CON_STOCK,
                    stock__gt=0,
                    stock_minimo__isnull=False,
                    stock__lte=F("stock_minimo"),
                ),
            ),
            agotados=Count(
                "id",
                filter=Q(
                    modalidad_abastecimiento=Producto.MODALIDAD_CON_STOCK,
                    stock__lte=0,
                ),
            ),
        )
        .order_by("categoria__codigo")
    ]

    resumen_productos = qs_prod.aggregate(
        total_activos=Count("id"),
        con_stock=Count("id", filter=Q(modalidad_abastecimiento=Producto.MODALIDAD_CON_STOCK)),
        bajo_pedido=Count("id", filter=Q(modalidad_abastecimiento=Producto.MODALIDAD_BAJO_PEDIDO)),
        stock_bajo=Count(
            "id",
            filter=Q(
                modalidad_abastecimiento=Producto.MODALIDAD_CON_STOCK,
                stock__gt=0,
                stock_minimo__isnull=False,
                stock__lte=F("stock_minimo"),
            ),
        ),
        agotados=Count(
            "id",
            filter=Q(
                modalidad_abastecimiento=Producto.MODALIDAD_CON_STOCK,
                stock__lte=0,
            ),
        ),
    )

    existencias_por_unidad = [
        {
            "unidad_codigo": r["unidad_stock__codigo"],
            "unidad_nombre": r["unidad_stock__nombre"],
            "cantidad_productos": r["cantidad_productos"],
            "stock_total": Decimal(str(r["stock_total"])).quantize(Decimal("0.0001")),
        }
        for r in qs_prod.filter(modalidad_abastecimiento=Producto.MODALIDAD_CON_STOCK)
        .values("unidad_stock__codigo", "unidad_stock__nombre")
        .annotate(
            cantidad_productos=Count("id"),
            stock_total=Coalesce(Sum("stock"), Value(Decimal("0.0000"))),
        )
        .order_by("unidad_stock__codigo")
    ]

    # Movimientos de stock (sin sumar distintas unidades)
    qs_mov = MovimientoStock.objects.all()
    if filtros.categoria:
        qs_mov = qs_mov.filter(producto__categoria__codigo=filtros.categoria)
    if filtros.fecha_desde is not None:
        qs_mov = qs_mov.filter(fecha__gte=inicio_dia_la_paz(filtros.fecha_desde))
    if filtros.fecha_hasta is not None:
        qs_mov = qs_mov.filter(fecha__lte=fin_dia_la_paz(filtros.fecha_hasta))

    mov_rows = list(
        qs_mov.values(
            "producto__unidad_stock__codigo",
            "producto__unidad_stock__nombre",
        ).annotate(
            total_movimientos=Count("id"),
            entradas_conteo=Count(
                "id",
                filter=Q(tipo_movimiento__codigo="CARGA_INICIAL")
                | Q(tipo_movimiento__codigo="AJUSTE", cantidad__gt=0),
            ),
            entradas_cantidad=Coalesce(
                Sum(
                    "cantidad",
                    filter=Q(tipo_movimiento__codigo="CARGA_INICIAL")
                    | Q(tipo_movimiento__codigo="AJUSTE", cantidad__gt=0),
                ),
                Value(Decimal("0.0000")),
            ),
            salidas_conteo=Count(
                "id",
                filter=Q(tipo_movimiento__codigo="VENTA")
                | Q(tipo_movimiento__codigo="AJUSTE", cantidad__lt=0),
            ),
            salidas_cantidad=Coalesce(
                Sum(
                    "cantidad",
                    filter=Q(tipo_movimiento__codigo="VENTA")
                    | Q(tipo_movimiento__codigo="AJUSTE", cantidad__lt=0),
                ),
                Value(Decimal("0.0000")),
            ),
            reversiones_conteo=Count("id", filter=Q(tipo_movimiento__codigo="REVERSA_VENTA")),
            reversiones_cantidad=Coalesce(
                Sum("cantidad", filter=Q(tipo_movimiento__codigo="REVERSA_VENTA")),
                Value(Decimal("0.0000")),
            ),
        )
    )

    movimientos_por_unidad = [
        {
            "unidad_codigo": r["producto__unidad_stock__codigo"],
            "unidad_nombre": r["producto__unidad_stock__nombre"],
            "total_movimientos": r["total_movimientos"],
            "entradas_conteo": r["entradas_conteo"],
            "entradas_cantidad": Decimal(str(r["entradas_cantidad"])),
            "salidas_conteo": r["salidas_conteo"],
            "salidas_cantidad_absoluta": abs(Decimal(str(r["salidas_cantidad"]))),
            "reversiones_conteo": r["reversiones_conteo"],
            "reversiones_cantidad": Decimal(str(r["reversiones_cantidad"])),
        }
        for r in sorted(mov_rows, key=lambda x: x["producto__unidad_stock__codigo"])
    ]

    # Productos más vendidos por categoría y unidad de medida (pedidos no cancelados)
    qs_det = DetalleProforma.objects.filter(
        producto__isnull=False,
        proforma__pedido__isnull=False,
    ).exclude(proforma__pedido__estado__codigo="CANCELADO")
    if filtros.categoria:
        qs_det = qs_det.filter(producto__categoria__codigo=filtros.categoria)
    if filtros.moneda:
        qs_det = qs_det.filter(proforma__moneda__codigo=filtros.moneda)
    if filtros.fecha_desde is not None:
        qs_det = qs_det.filter(proforma__fecha__gte=filtros.fecha_desde)
    if filtros.fecha_hasta is not None:
        qs_det = qs_det.filter(proforma__fecha__lte=filtros.fecha_hasta)

    mas_vendidos = [
        {
            "producto_id": r["producto_id"],
            "sku": r["producto__sku"],
            "nombre": r["producto__nombre"],
            "categoria_codigo": r["producto__categoria__codigo"],
            "categoria_nombre": r["producto__categoria__nombre"],
            "unidad_codigo": r["unidad__codigo"],
            "unidad_nombre": r["unidad__nombre"],
            "moneda": r["proforma__moneda__codigo"],
            "cantidad_vendida": Decimal(str(r["cantidad_vendida"])),
            "importe_total": redondear_decimal(r["importe_total"]),
            "pedidos_count": r["pedidos_count"],
        }
        for r in qs_det.values(
            "producto_id",
            "producto__sku",
            "producto__nombre",
            "producto__categoria__codigo",
            "producto__categoria__nombre",
            "unidad__codigo",
            "unidad__nombre",
            "proforma__moneda__codigo",
        )
        .annotate(
            cantidad_vendida=Coalesce(Sum("cantidad"), Value(Decimal("0.0000"))),
            importe_total=Coalesce(Sum("total"), Value(CERO)),
            pedidos_count=Count("proforma__pedido__id", distinct=True),
        )
        .order_by("producto__categoria__codigo", "unidad__codigo", "-cantidad_vendida")
    ]

    return {
        "resumen": {
            "total_activos": resumen_productos["total_activos"] or 0,
            "con_stock": resumen_productos["con_stock"] or 0,
            "bajo_pedido": resumen_productos["bajo_pedido"] or 0,
            "stock_bajo": resumen_productos["stock_bajo"] or 0,
            "agotados": resumen_productos["agotados"] or 0,
        },
        "por_categoria": por_categoria,
        "existencias_por_unidad": existencias_por_unidad,
        "movimientos_por_unidad": movimientos_por_unidad,
        "mas_vendidos": paginar_lista(mas_vendidos, filtros.page, filtros.page_size),
    }


def obtener_disponibilidad_comercial(filtros: DashboardFilterParams) -> dict:
    """Resumen de disponibilidad para el encargado de tienda (CON_STOCK vs BAJO_PEDIDO)."""
    qs_prod = _filtrar_productos(filtros).order_by("modalidad_abastecimiento", "stock", "nombre")

    resumen = qs_prod.aggregate(
        total_activos=Count("id"),
        con_stock_disponible=Count(
            "id",
            filter=Q(modalidad_abastecimiento=Producto.MODALIDAD_CON_STOCK, stock__gt=0),
        ),
        con_stock_bajo=Count(
            "id",
            filter=Q(
                modalidad_abastecimiento=Producto.MODALIDAD_CON_STOCK,
                stock__gt=0,
                stock_minimo__isnull=False,
                stock__lte=F("stock_minimo"),
            ),
        ),
        con_stock_agotado=Count(
            "id",
            filter=Q(modalidad_abastecimiento=Producto.MODALIDAD_CON_STOCK, stock__lte=0),
        ),
        bajo_pedido=Count(
            "id",
            filter=Q(modalidad_abastecimiento=Producto.MODALIDAD_BAJO_PEDIDO),
        ),
    )

    productos = []
    for p in qs_prod:
        if p.modalidad_abastecimiento == Producto.MODALIDAD_BAJO_PEDIDO:
            estado_disp = "BAJO_PEDIDO"
        elif p.stock <= 0:
            estado_disp = "AGOTADO"
        elif p.stock_minimo is not None and p.stock <= p.stock_minimo:
            estado_disp = "STOCK_BAJO"
        else:
            estado_disp = "DISPONIBLE"

        productos.append(
            {
                "producto_id": p.id,
                "sku": p.sku,
                "nombre": p.nombre,
                "categoria_codigo": p.categoria.codigo,
                "categoria_nombre": p.categoria.nombre,
                "modalidad_abastecimiento": p.modalidad_abastecimiento,
                "stock": p.stock,
                "stock_minimo": p.stock_minimo,
                "unidad_codigo": p.unidad_stock.codigo,
                "unidad_nombre": p.unidad_stock.nombre,
                "estado_disponibilidad": estado_disp,
            }
        )

    return {
        "resumen": {
            "total_activos": resumen["total_activos"] or 0,
            "con_stock_disponible": resumen["con_stock_disponible"] or 0,
            "con_stock_bajo": resumen["con_stock_bajo"] or 0,
            "con_stock_agotado": resumen["con_stock_agotado"] or 0,
            "bajo_pedido": resumen["bajo_pedido"] or 0,
        },
        "productos": paginar_lista(productos, filtros.page, filtros.page_size),
    }
