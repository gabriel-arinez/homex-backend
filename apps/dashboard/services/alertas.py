from __future__ import annotations

from datetime import timedelta

from django.db.models import F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from apps.catalogo.models import Producto
from apps.dashboard.filters import DashboardFilterParams
from apps.dashboard.services.common import (
    CERO,
    fecha_referencia_analitica,
    nombre_cliente_proforma,
    nombre_usuario,
    redondear_decimal,
)
from apps.dashboard.services.taller import filtro_fabricacion_a_medida
from apps.ordenes_trabajo.models import OrdenTrabajo
from apps.pedidos.models import Pedido
from apps.proformas.models import Proforma
from apps.proformas.vigencia import fecha_limite
from apps.recibos.models import Recibo


def obtener_alertas_prioritarias_admin(filtros: DashboardFilterParams) -> dict:
    """Registros concretos de alertas prioritarias para el administrador."""
    hoy = fecha_referencia_analitica()
    limite_7d = hoy + timedelta(days=7)
    top_n = min(filtros.page_size, 20)

    # 1. Proformas próximas a vencer (en los siguientes 7 días)
    qs_prof = (
        Proforma.objects.filter(
            estado__codigo__in=["EN_REVISION", "ENVIADA"],
            validez_oferta__isnull=False,
            validez_oferta__gt=0,
        )
        .select_related("cliente", "vendedor", "estado", "moneda")
        .order_by("fecha", "id")
    )
    if filtros.vendedor_id is not None:
        qs_prof = qs_prof.filter(vendedor_id=filtros.vendedor_id)
    if filtros.moneda:
        qs_prof = qs_prof.filter(moneda__codigo=filtros.moneda)

    proformas_vencer = []
    for p in qs_prof:
        lim = fecha_limite(p.fecha, p.validez_oferta)
        if lim is not None and hoy <= lim <= limite_7d:
            proformas_vencer.append(
                {
                    "proforma_id": p.id,
                    "numero": p.numero,
                    "cliente_nombre": nombre_cliente_proforma(p),
                    "vendedor_nombre": nombre_usuario(p.vendedor),
                    "fecha_vencimiento": lim.isoformat(),
                    "dias_restantes": (lim - hoy).days,
                    "moneda": p.moneda.codigo,
                    "total": redondear_decimal(p.total),
                }
            )
    proformas_vencer.sort(key=lambda x: x["dias_restantes"])

    # 2. Pedidos retrasados (con fecha_entrega < hoy y no entregados ni cancelados)
    qs_ped_ret = (
        Pedido.objects.filter(
            ordentrabajo__fecha_entrega__lt=hoy,
        )
        .exclude(estado__codigo__in=["ENTREGADO", "CANCELADO"])
        .select_related("proforma__cliente", "proforma__vendedor", "estado", "ordentrabajo")
        .order_by("ordentrabajo__fecha_entrega", "id")
    )
    if filtros.vendedor_id is not None:
        qs_ped_ret = qs_ped_ret.filter(proforma__vendedor_id=filtros.vendedor_id)

    pedidos_retrasados = [
        {
            "pedido_id": ped.id,
            "proforma_numero": ped.proforma.numero,
            "cliente_nombre": nombre_cliente_proforma(ped.proforma),
            "vendedor_nombre": nombre_usuario(ped.proforma.vendedor),
            "estado_codigo": ped.estado.codigo,
            "fecha_entrega_prevista": ped.ordentrabajo.fecha_entrega.isoformat(),
            "dias_retraso": (hoy - ped.ordentrabajo.fecha_entrega).days,
        }
        for ped in qs_ped_ret[:top_n]
    ]

    # 3. Fabricaciones retrasadas (OT funcional no terminada/cancelada con fecha_entrega < hoy)
    qs_fab_ret = (
        OrdenTrabajo.objects.filter(
            filtro_fabricacion_a_medida(),
            fecha_entrega__lt=hoy,
        )
        .exclude(estado__codigo__in=["TERMINADA", "CANCELADA"])
        .select_related("pedido__proforma__cliente", "pedido__proforma__vendedor", "estado")
        .order_by("fecha_entrega", "id")
    )
    if filtros.vendedor_id is not None:
        qs_fab_ret = qs_fab_ret.filter(pedido__proforma__vendedor_id=filtros.vendedor_id)

    fabricaciones_retrasadas = [
        {
            "orden_trabajo_id": ot.id,
            "numero_ot": ot.numero,
            "cliente_nombre": nombre_cliente_proforma(ot.pedido.proforma),
            "estado_codigo": ot.estado.codigo,
            "fecha_entrega_prevista": ot.fecha_entrega.isoformat(),
            "dias_retraso": (hoy - ot.fecha_entrega).days,
        }
        for ot in qs_fab_ret[:top_n]
    ]

    # 4. Saldos pendientes de pedidos entregados
    cobros_sq = (
        Recibo.objects.filter(pedido=OuterRef("pk"), estado="EMITIDO")
        .values("pedido")
        .annotate(s=Sum("pago_actual"))
        .values("s")[:1]
    )
    qs_saldos = (
        Pedido.objects.filter(estado__codigo="ENTREGADO")
        .select_related("proforma__cliente", "proforma__moneda")
        .annotate(
            cobrado=Coalesce(Subquery(cobros_sq), Value(CERO)),
            saldo=F("proforma__total") - Coalesce(Subquery(cobros_sq), Value(CERO)),
        )
        .filter(saldo__gt=CERO)
        .order_by("-saldo", "id")
    )
    if filtros.vendedor_id is not None:
        qs_saldos = qs_saldos.filter(proforma__vendedor_id=filtros.vendedor_id)
    if filtros.moneda:
        qs_saldos = qs_saldos.filter(proforma__moneda__codigo=filtros.moneda)

    saldos_entregados = [
        {
            "pedido_id": ped.id,
            "proforma_numero": ped.proforma.numero,
            "cliente_nombre": nombre_cliente_proforma(ped.proforma),
            "moneda": ped.proforma.moneda.codigo,
            "saldo_pendiente": redondear_decimal(ped.saldo),
            "fecha_entrega_efectiva": (
                ped.fecha_entrega_efectiva.isoformat() if ped.fecha_entrega_efectiva else None
            ),
        }
        for ped in qs_saldos[:top_n]
    ]

    # 5. Productos con stock bajo o agotados (CON_STOCK)
    qs_stock = (
        Producto.objects.filter(
            activo=True,
            modalidad_abastecimiento=Producto.MODALIDAD_CON_STOCK,
        )
        .filter(Q(stock__lte=0) | Q(stock_minimo__isnull=False, stock__lte=F("stock_minimo")))
        .select_related("categoria", "unidad_stock")
        .order_by("stock", "id")
    )
    if filtros.categoria:
        qs_stock = qs_stock.filter(categoria__codigo=filtros.categoria)

    productos_stock_bajo = [
        {
            "producto_id": p.id,
            "sku": p.sku,
            "nombre": p.nombre,
            "categoria_codigo": p.categoria.codigo,
            "stock": p.stock,
            "stock_minimo": p.stock_minimo,
            "unidad_codigo": p.unidad_stock.codigo,
            "estado_stock": "AGOTADO" if p.stock <= 0 else "STOCK_BAJO",
        }
        for p in qs_stock[:top_n]
    ]

    return {
        "proformas_proximas_vencer": proformas_vencer[:top_n],
        "pedidos_retrasados": pedidos_retrasados,
        "fabricaciones_retrasadas": fabricaciones_retrasadas,
        "saldos_pedidos_entregados": saldos_entregados,
        "productos_stock_bajo": productos_stock_bajo,
    }
