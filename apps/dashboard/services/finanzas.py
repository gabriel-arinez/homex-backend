from __future__ import annotations

from django.db.models import Count, Exists, F, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from apps.dashboard.filters import DashboardFilterParams
from apps.dashboard.services.common import (
    CERO,
    calcular_porcentaje,
    fin_dia_la_paz,
    formatear_periodo,
    inicio_dia_la_paz,
    nombre_cliente_proforma,
    paginar_lista,
    redondear_decimal,
    trunc_temporal,
)
from apps.pedidos.models import Pedido
from apps.proformas.models import DetalleProforma
from apps.recibos.models import Recibo


def _filtrar_pedidos_vigentes(
    filtros: DashboardFilterParams,
    *,
    vendedor_id: int | None = None,
    aplicar_periodo: bool = True,
):
    uid = vendedor_id if vendedor_id is not None else filtros.vendedor_id
    qs = Pedido.objects.exclude(estado__codigo="CANCELADO")
    if uid is not None:
        qs = qs.filter(proforma__vendedor_id=uid)
    if filtros.moneda:
        qs = qs.filter(proforma__moneda__codigo=filtros.moneda)
    if filtros.categoria:
        qs = qs.filter(
            Exists(
                DetalleProforma.objects.filter(
                    proforma_id=OuterRef("proforma_id"),
                    producto__categoria__codigo=filtros.categoria,
                )
            )
        )
    if aplicar_periodo:
        if filtros.fecha_desde is not None:
            qs = qs.filter(fecha_confirmacion__gte=inicio_dia_la_paz(filtros.fecha_desde))
        if filtros.fecha_hasta is not None:
            qs = qs.filter(fecha_confirmacion__lte=fin_dia_la_paz(filtros.fecha_hasta))
    return qs


def _cartera_por_moneda(
    filtros: DashboardFilterParams,
    *,
    vendedor_id: int | None = None,
) -> tuple[list[dict], list[dict]]:
    """Calcula cartera de pedidos confirmados en el período, cobros del período y cancelados."""
    uid = vendedor_id if vendedor_id is not None else filtros.vendedor_id
    qs_ped = _filtrar_pedidos_vigentes(filtros, vendedor_id=uid, aplicar_periodo=True)

    ped_rows = list(
        qs_ped.values("proforma__moneda__codigo").annotate(
            importe_pedidos=Coalesce(Sum("proforma__total"), Value(CERO)),
            cantidad_pedidos=Count("id"),
        )
    )

    # Cobros acumulados de la cartera filtrada (todos los recibos EMITIDO de esos pedidos)
    rec_acum_rows = {
        r["pedido__proforma__moneda__codigo"]: redondear_decimal(r["total"])
        for r in Recibo.objects.filter(estado="EMITIDO", pedido__in=qs_ped)
        .values("pedido__proforma__moneda__codigo")
        .annotate(total=Coalesce(Sum("pago_actual"), Value(CERO)))
    }

    # Cobros válidos realizados durante el período (por recibo.fecha, sobre cartera vigente)
    rec_periodo = Recibo.objects.filter(estado="EMITIDO").exclude(
        pedido__estado__codigo="CANCELADO"
    )
    if uid is not None:
        rec_periodo = rec_periodo.filter(pedido__proforma__vendedor_id=uid)
    if filtros.moneda:
        rec_periodo = rec_periodo.filter(pedido__proforma__moneda__codigo=filtros.moneda)
    if filtros.categoria:
        rec_periodo = rec_periodo.filter(
            Exists(
                DetalleProforma.objects.filter(
                    proforma_id=OuterRef("pedido__proforma_id"),
                    producto__categoria__codigo=filtros.categoria,
                )
            )
        )
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


def _nombre_canonico_cliente(prof) -> str:
    if prof.cliente_id is not None:
        cli = prof.cliente
        nombre = " ".join(p.strip() for p in [cli.nombres or "", cli.apellidos or ""] if p.strip())
        if nombre:
            return nombre
        if cli.empresa:
            return cli.empresa.strip()
    return nombre_cliente_proforma(prof)


def obtener_finanzas_admin(filtros: DashboardFilterParams) -> dict:
    resumen_monedas, cancelados = _cartera_por_moneda(filtros)

    cobros_sq = (
        Recibo.objects.filter(pedido=OuterRef("pk"), estado="EMITIDO")
        .values("pedido")
        .annotate(s=Sum("pago_actual"))
        .values("s")[:1]
    )
    qs_ped = (
        _filtrar_pedidos_vigentes(filtros, aplicar_periodo=True)
        .select_related("proforma__cliente", "proforma__moneda", "proforma__vendedor", "estado")
        .annotate(
            cobrado=Coalesce(Subquery(cobros_sq), Value(CERO)),
            saldo=F("proforma__total") - Coalesce(Subquery(cobros_sq), Value(CERO)),
        )
        .filter(saldo__gt=CERO)
    )

    entregados_con_saldo = []
    # Agrupar por (cliente_id, moneda) cuando existe cliente_id para no fragmentar por snapshots.
    clientes_por_moneda: dict[str, dict[tuple[int | None, str], dict]] = {}

    for ped in qs_ped.order_by("-saldo", "id"):
        prof = ped.proforma
        mon = prof.moneda.codigo
        cli_nom_ped = nombre_cliente_proforma(prof)
        saldo_val = redondear_decimal(ped.saldo)
        if ped.estado.codigo == "ENTREGADO":
            entregados_con_saldo.append(
                {
                    "pedido_id": ped.id,
                    "proforma_id": prof.id,
                    "proforma_numero": prof.numero,
                    "cliente_id": prof.cliente_id,
                    "cliente_nombre": cli_nom_ped,
                    "moneda": mon,
                    "total_pedido": redondear_decimal(prof.total),
                    "cobrado": redondear_decimal(ped.cobrado),
                    "saldo_pendiente": saldo_val,
                    "fecha_entrega_efectiva": ped.fecha_entrega_efectiva,
                }
            )
        cli_nom_canon = _nombre_canonico_cliente(prof)
        key = (prof.cliente_id, "" if prof.cliente_id is not None else cli_nom_canon)
        bucket = clientes_por_moneda.setdefault(mon, {})
        entry = bucket.setdefault(
            key,
            {
                "cliente_id": prof.cliente_id,
                "cliente_nombre": cli_nom_canon,
                "moneda": mon,
                "cantidad_pedidos": 0,
                "saldo_pendiente": CERO,
            },
        )
        entry["cantidad_pedidos"] += 1
        entry["saldo_pendiente"] = redondear_decimal(entry["saldo_pendiente"] + saldo_val)

    clientes_mayores_saldos_por_moneda = []
    for mon in sorted(clientes_por_moneda.keys()):
        ranking = sorted(
            clientes_por_moneda[mon].values(),
            key=lambda x: (-x["saldo_pendiente"], x["cliente_nombre"]),
        )[: filtros.page_size]
        clientes_mayores_saldos_por_moneda.append({"moneda": mon, "clientes": ranking})

    # Evolución temporal de cobros válidos (por recibo.fecha)
    rec_qs = Recibo.objects.filter(estado="EMITIDO").exclude(pedido__estado__codigo="CANCELADO")
    if filtros.vendedor_id is not None:
        rec_qs = rec_qs.filter(pedido__proforma__vendedor_id=filtros.vendedor_id)
    if filtros.moneda:
        rec_qs = rec_qs.filter(pedido__proforma__moneda__codigo=filtros.moneda)
    if filtros.categoria:
        rec_qs = rec_qs.filter(
            Exists(
                DetalleProforma.objects.filter(
                    proforma_id=OuterRef("pedido__proforma_id"),
                    producto__categoria__codigo=filtros.categoria,
                )
            )
        )
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
        "clientes_mayores_saldos_por_moneda": clientes_mayores_saldos_por_moneda,
        "evolucion_cobros": [
            {"moneda": mon, "puntos": pts} for mon, pts in sorted(evo_por_moneda.items())
        ],
    }
