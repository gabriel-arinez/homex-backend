from __future__ import annotations

from django.db.models import Count, F, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from apps.dashboard.filters import DashboardFilterParams
from apps.dashboard.services.common import (
    CERO,
    calcular_porcentaje,
    formatear_periodo,
    nombre_cliente_proforma,
    paginar_lista,
    redondear_decimal,
    trunc_temporal,
)
from apps.pedidos.models import Pedido
from apps.recibos.models import Recibo


def _cartera_por_moneda(
    filtros: DashboardFilterParams,
    *,
    vendedor_id: int | None = None,
) -> tuple[list[dict], list[dict]]:
    """Calcula importes de pedidos vigentes, cobros válidos, saldos y cobros de cancelados."""
    uid = vendedor_id if vendedor_id is not None else filtros.vendedor_id

    qs_ped = Pedido.objects.exclude(estado__codigo="CANCELADO")
    if uid is not None:
        qs_ped = qs_ped.filter(proforma__vendedor_id=uid)
    if filtros.moneda:
        qs_ped = qs_ped.filter(proforma__moneda__codigo=filtros.moneda)
    if filtros.fecha_desde is not None:
        qs_ped = qs_ped.filter(proforma__fecha__gte=filtros.fecha_desde)
    if filtros.fecha_hasta is not None:
        qs_ped = qs_ped.filter(proforma__fecha__lte=filtros.fecha_hasta)

    ped_rows = list(
        qs_ped.values("proforma__moneda__codigo").annotate(
            importe_pedidos=Coalesce(Sum("proforma__total"), Value(CERO)),
            cantidad_pedidos=Count("id"),
        )
    )

    # Cobros acumulados de la cartera vigente (sin filtrar recibo.fecha por período,
    # sobre los pedidos de la cartera filtrada, sin recibos anulados ni pedidos cancelados)
    rec_cartera = Recibo.objects.filter(estado="EMITIDO", pedido__in=qs_ped)
    rec_acum_rows = {
        r["pedido__proforma__moneda__codigo"]: redondear_decimal(r["total"])
        for r in rec_cartera.values("pedido__proforma__moneda__codigo").annotate(
            total=Coalesce(Sum("pago_actual"), Value(CERO))
        )
    }

    # Cobros válidos emitidos dentro del período seleccionado (por recibo.fecha)
    rec_periodo = Recibo.objects.filter(estado="EMITIDO").exclude(
        pedido__estado__codigo="CANCELADO"
    )
    if uid is not None:
        rec_periodo = rec_periodo.filter(pedido__proforma__vendedor_id=uid)
    if filtros.moneda:
        rec_periodo = rec_periodo.filter(pedido__proforma__moneda__codigo=filtros.moneda)
    if filtros.fecha_desde is not None:
        rec_periodo = rec_periodo.filter(fecha__gte=filtros.fecha_desde)
    if filtros.fecha_hasta is not None:
        rec_periodo = rec_periodo.filter(fecha__lte=filtros.fecha_hasta)

    rec_per_rows = {
        r["pedido__proforma__moneda__codigo"]: redondear_decimal(r["total"])
        for r in rec_periodo.values("pedido__proforma__moneda__codigo").annotate(
            total=Coalesce(Sum("pago_actual"), Value(CERO))
        )
    }

    # Cobros asociados a pedidos cancelados (separados explícitamente, nunca mezclados)
    rec_cancelados = Recibo.objects.filter(estado="EMITIDO", pedido__estado__codigo="CANCELADO")
    if uid is not None:
        rec_cancelados = rec_cancelados.filter(pedido__proforma__vendedor_id=uid)
    if filtros.moneda:
        rec_cancelados = rec_cancelados.filter(pedido__proforma__moneda__codigo=filtros.moneda)
    if filtros.fecha_desde is not None:
        rec_cancelados = rec_cancelados.filter(fecha__gte=filtros.fecha_desde)
    if filtros.fecha_hasta is not None:
        rec_cancelados = rec_cancelados.filter(fecha__lte=filtros.fecha_hasta)

    rec_canc_rows = list(
        rec_cancelados.values("pedido__proforma__moneda__codigo").annotate(
            cantidad_recibos=Count("id"),
            total=Coalesce(Sum("pago_actual"), Value(CERO)),
        )
    )

    monedas = sorted(
        {r["proforma__moneda__codigo"] for r in ped_rows}
        | set(rec_acum_rows.keys())
        | set(rec_per_rows.keys())
    )
    ped_map = {r["proforma__moneda__codigo"]: r for r in ped_rows}

    resumen_monedas = []
    for mon in monedas:
        imp = redondear_decimal(ped_map.get(mon, {}).get("importe_pedidos", CERO))
        cob_acum = rec_acum_rows.get(mon, CERO)
        cob_per = rec_per_rows.get(mon, CERO)
        saldo = redondear_decimal(imp - cob_acum)
        resumen_monedas.append(
            {
                "moneda": mon,
                "importe_pedidos_no_cancelados": imp,
                "cobros_validos_periodo": cob_per,
                "cobros_acumulados_cartera_vigente": cob_acum,
                "saldo_pendiente": saldo,
                "porcentaje_cobrado": calcular_porcentaje(cob_acum, imp),
            }
        )

    cancelados_monedas = [
        {
            "moneda": r["pedido__proforma__moneda__codigo"],
            "cantidad_recibos": r["cantidad_recibos"],
            "importe": redondear_decimal(r["total"]),
        }
        for r in rec_canc_rows
    ]
    return resumen_monedas, cancelados_monedas


def obtener_resumen_financiero_vendedor(
    filtros: DashboardFilterParams,
    *,
    vendedor_id: int | None = None,
) -> dict:
    resumen, cancelados = _cartera_por_moneda(filtros, vendedor_id=vendedor_id)
    return {
        "por_moneda": resumen,
        "cobros_pedidos_cancelados": cancelados,
    }


def obtener_finanzas_admin(filtros: DashboardFilterParams) -> dict:
    resumen_monedas, cancelados = _cartera_por_moneda(filtros)

    cobros_sq = (
        Recibo.objects.filter(pedido=OuterRef("pk"), estado="EMITIDO")
        .values("pedido")
        .annotate(s=Sum("pago_actual"))
        .values("s")[:1]
    )
    qs_ped = (
        Pedido.objects.exclude(estado__codigo="CANCELADO")
        .select_related("proforma__cliente", "proforma__moneda", "proforma__vendedor", "estado")
        .annotate(
            cobrado=Coalesce(Subquery(cobros_sq), Value(CERO)),
            saldo=F("proforma__total") - Coalesce(Subquery(cobros_sq), Value(CERO)),
        )
        .filter(saldo__gt=CERO)
    )
    if filtros.vendedor_id is not None:
        qs_ped = qs_ped.filter(proforma__vendedor_id=filtros.vendedor_id)
    if filtros.moneda:
        qs_ped = qs_ped.filter(proforma__moneda__codigo=filtros.moneda)
    if filtros.fecha_desde is not None:
        qs_ped = qs_ped.filter(proforma__fecha__gte=filtros.fecha_desde)
    if filtros.fecha_hasta is not None:
        qs_ped = qs_ped.filter(proforma__fecha__lte=filtros.fecha_hasta)

    # Pedidos entregados con saldo pendiente
    entregados_con_saldo = []
    # Acumular por cliente + moneda (nunca sumar distintas monedas)
    clientes_saldo: dict[tuple[int | None, str, str], dict] = {}

    for ped in qs_ped.order_by("-saldo", "id"):
        prof = ped.proforma
        mon = prof.moneda.codigo
        cli_nom = nombre_cliente_proforma(prof)
        saldo_val = redondear_decimal(ped.saldo)
        if ped.estado.codigo == "ENTREGADO":
            entregados_con_saldo.append(
                {
                    "pedido_id": ped.id,
                    "proforma_id": prof.id,
                    "proforma_numero": prof.numero,
                    "cliente_id": prof.cliente_id,
                    "cliente_nombre": cli_nom,
                    "moneda": mon,
                    "total_pedido": redondear_decimal(prof.total),
                    "cobrado": redondear_decimal(ped.cobrado),
                    "saldo_pendiente": saldo_val,
                    "fecha_entrega_efectiva": (
                        ped.fecha_entrega_efectiva.isoformat()
                        if ped.fecha_entrega_efectiva
                        else None
                    ),
                }
            )
        key = (prof.cliente_id, cli_nom, mon)
        entry = clientes_saldo.setdefault(
            key,
            {
                "cliente_id": prof.cliente_id,
                "cliente_nombre": cli_nom,
                "moneda": mon,
                "cantidad_pedidos": 0,
                "saldo_pendiente": CERO,
            },
        )
        entry["cantidad_pedidos"] += 1
        entry["saldo_pendiente"] = redondear_decimal(entry["saldo_pendiente"] + saldo_val)

    clientes_ordenados = sorted(
        clientes_saldo.values(),
        key=lambda x: (-x["saldo_pendiente"], x["cliente_nombre"]),
    )

    # Evolución temporal de cobros válidos
    rec_qs = Recibo.objects.filter(estado="EMITIDO").exclude(pedido__estado__codigo="CANCELADO")
    if filtros.vendedor_id is not None:
        rec_qs = rec_qs.filter(pedido__proforma__vendedor_id=filtros.vendedor_id)
    if filtros.moneda:
        rec_qs = rec_qs.filter(pedido__proforma__moneda__codigo=filtros.moneda)
    if filtros.fecha_desde is not None:
        rec_qs = rec_qs.filter(fecha__gte=filtros.fecha_desde)
    if filtros.fecha_hasta is not None:
        rec_qs = rec_qs.filter(fecha__lte=filtros.fecha_hasta)

    evo_rows = (
        rec_qs.annotate(periodo=trunc_temporal("fecha", filtros.granularidad, is_datetime=False))
        .values("periodo", "pedido__proforma__moneda__codigo")
        .annotate(
            cantidad_recibos=Count("id"),
            monto_cobrado=Coalesce(Sum("pago_actual"), Value(CERO)),
        )
        .order_by("periodo", "pedido__proforma__moneda__codigo")
    )
    evo_por_moneda: dict[str, list[dict]] = {}
    for r in evo_rows:
        mon = r["pedido__proforma__moneda__codigo"]
        evo_por_moneda.setdefault(mon, []).append(
            {
                "periodo": formatear_periodo(r["periodo"]),
                "cantidad_recibos": r["cantidad_recibos"],
                "monto_cobrado": redondear_decimal(r["monto_cobrado"]),
            }
        )

    return {
        "por_moneda": resumen_monedas,
        "cobros_pedidos_cancelados": cancelados,
        "pedidos_entregados_con_saldo": paginar_lista(
            entregados_con_saldo, filtros.page, filtros.page_size
        ),
        "clientes_mayores_saldos": clientes_ordenados[: filtros.page_size],
        "evolucion_cobros": [
            {"moneda": mon, "puntos": pts} for mon, pts in sorted(evo_por_moneda.items())
        ],
    }
