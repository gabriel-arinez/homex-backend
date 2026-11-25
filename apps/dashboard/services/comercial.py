from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Count, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from apps.dashboard.filters import DashboardFilterParams
from apps.dashboard.services.common import (
    CERO,
    calcular_porcentaje,
    fecha_referencia_analitica,
    fin_dia_la_paz,
    formatear_periodo,
    inicio_dia_la_paz,
    nombre_cliente_proforma,
    nombre_usuario,
    paginar_lista,
    periodo_anterior,
    redondear_decimal,
    trunc_temporal,
    variacion_numerica,
)
from apps.pedidos.models import Pedido
from apps.proformas.models import Proforma
from apps.proformas.vigencia import fecha_limite
from apps.recibos.models import Recibo

User = get_user_model()


def _filtrar_proformas_base(
    filtros: DashboardFilterParams,
    *,
    vendedor_id: int | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    aplicar_estado_comercial: bool = True,
):
    qs = Proforma.objects.all()
    uid = vendedor_id if vendedor_id is not None else filtros.vendedor_id
    if uid is not None:
        qs = qs.filter(vendedor_id=uid)
    if filtros.moneda:
        qs = qs.filter(moneda__codigo=filtros.moneda)
    f_desde = fecha_desde if fecha_desde is not None else filtros.fecha_desde
    f_hasta = fecha_hasta if fecha_hasta is not None else filtros.fecha_hasta
    if f_desde is not None:
        qs = qs.filter(fecha__gte=f_desde)
    if f_hasta is not None:
        qs = qs.filter(fecha__lte=f_hasta)
    if aplicar_estado_comercial and filtros.estado_comercial:
        qs = qs.filter(
            Q(estado__codigo=filtros.estado_comercial)
            | Q(pedido__estado__codigo=filtros.estado_comercial)
        )
    return qs


def _conteos_comerciales_periodo(
    filtros: DashboardFilterParams,
    *,
    vendedor_id: int | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
) -> dict:
    qs = _filtrar_proformas_base(
        filtros,
        vendedor_id=vendedor_id,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    res = qs.aggregate(
        total_proformas=Count("id"),
        borradores=Count("id", filter=Q(estado__codigo="BORRADOR")),
        proformas_formalizadas=Count("id", filter=~Q(estado__codigo="BORRADOR")),
    )
    formalizadas_qs = qs.exclude(estado__codigo="BORRADOR")
    pedidos_cohorte = Pedido.objects.filter(proforma__in=formalizadas_qs)
    ped_res = pedidos_cohorte.aggregate(
        pedidos_generados=Count("id"),
        pedidos_no_cancelados=Count("id", filter=~Q(estado__codigo="CANCELADO")),
    )

    formalizadas = res["proformas_formalizadas"] or 0
    pedidos_gen = ped_res["pedidos_generados"] or 0
    return {
        "total_proformas": res["total_proformas"] or 0,
        "borradores": res["borradores"] or 0,
        "proformas_formalizadas": formalizadas,
        "pedidos_generados": pedidos_gen,
        "pedidos_no_cancelados": ped_res["pedidos_no_cancelados"] or 0,
        "tasa_conversion_cohorte": calcular_porcentaje(pedidos_gen, formalizadas),
    }


def _distribuciones_actuales(
    filtros: DashboardFilterParams,
    *,
    vendedor_id: int | None = None,
) -> tuple[list[dict], list[dict]]:
    # Estado actual de registros (no reconstruye historial).
    qs_prof = _filtrar_proformas_base(
        filtros,
        vendedor_id=vendedor_id,
        aplicar_estado_comercial=False,
    )
    dist_proformas = [
        {
            "codigo": row["estado__codigo"],
            "nombre": row["estado__nombre"],
            "cantidad": row["cantidad"],
        }
        for row in qs_prof.values("estado__codigo", "estado__nombre")
        .annotate(cantidad=Count("id"))
        .order_by("-cantidad", "estado__codigo")
    ]

    qs_ped = Pedido.objects.all()
    uid = vendedor_id if vendedor_id is not None else filtros.vendedor_id
    if uid is not None:
        qs_ped = qs_ped.filter(proforma__vendedor_id=uid)
    if filtros.moneda:
        qs_ped = qs_ped.filter(proforma__moneda__codigo=filtros.moneda)
    if filtros.fecha_desde is not None:
        qs_ped = qs_ped.filter(proforma__fecha__gte=filtros.fecha_desde)
    if filtros.fecha_hasta is not None:
        qs_ped = qs_ped.filter(proforma__fecha__lte=filtros.fecha_hasta)

    dist_pedidos = [
        {
            "codigo": row["estado__codigo"],
            "nombre": row["estado__nombre"],
            "cantidad": row["cantidad"],
        }
        for row in qs_ped.values("estado__codigo", "estado__nombre")
        .annotate(cantidad=Count("id"))
        .order_by("-cantidad", "estado__codigo")
    ]
    return dist_proformas, dist_pedidos


def obtener_indicadores_comerciales(
    filtros: DashboardFilterParams,
    *,
    vendedor_id: int | None = None,
) -> dict:
    actual = _conteos_comerciales_periodo(filtros, vendedor_id=vendedor_id)
    prev_rango = periodo_anterior(filtros.fecha_desde, filtros.fecha_hasta)
    if prev_rango is not None:
        anterior = _conteos_comerciales_periodo(
            filtros,
            vendedor_id=vendedor_id,
            fecha_desde=prev_rango[0],
            fecha_hasta=prev_rango[1],
        )
        comparaciones = {
            "periodo_anterior": {
                "fecha_desde": prev_rango[0].isoformat(),
                "fecha_hasta": prev_rango[1].isoformat(),
            },
            "proformas_formalizadas": variacion_numerica(
                actual["proformas_formalizadas"], anterior["proformas_formalizadas"]
            ),
            "borradores": variacion_numerica(actual["borradores"], anterior["borradores"]),
            "pedidos_generados": variacion_numerica(
                actual["pedidos_generados"], anterior["pedidos_generados"]
            ),
            "pedidos_no_cancelados": variacion_numerica(
                actual["pedidos_no_cancelados"], anterior["pedidos_no_cancelados"]
            ),
        }
    else:
        comparaciones = None

    dist_proformas, dist_pedidos = _distribuciones_actuales(filtros, vendedor_id=vendedor_id)
    return {
        **actual,
        "distribucion_proformas_estado": dist_proformas,
        "distribucion_pedidos_estado": dist_pedidos,
        "comparaciones_periodo_anterior": comparaciones,
        "limitaciones": [
            "No existe tabla de historial de estados para proformas; la cohorte formalizada "
            "agrupa proformas con estado distinto de BORRADOR por su fecha comercial "
            "(proformas.fecha)."
        ],
    }


def obtener_evolucion_comercial(
    filtros: DashboardFilterParams,
    *,
    vendedor_id: int | None = None,
) -> dict:
    uid = vendedor_id if vendedor_id is not None else filtros.vendedor_id
    gran = filtros.granularidad

    # 1. Proformas formalizadas por proforma.fecha
    qs_prof = _filtrar_proformas_base(
        filtros, vendedor_id=uid, aplicar_estado_comercial=False
    ).exclude(estado__codigo="BORRADOR")
    serie_prof = {
        formatear_periodo(r["periodo"]): r["cantidad"]
        for r in qs_prof.annotate(periodo=trunc_temporal("fecha", gran, is_datetime=False))
        .values("periodo")
        .annotate(cantidad=Count("id"))
        .order_by("periodo")
    }

    # 2. Pedidos generados e importe de pedidos no cancelados por moneda (sin mezclar monedas)
    qs_ped = Pedido.objects.all()
    if uid is not None:
        qs_ped = qs_ped.filter(proforma__vendedor_id=uid)
    if filtros.moneda:
        qs_ped = qs_ped.filter(proforma__moneda__codigo=filtros.moneda)
    if filtros.fecha_desde is not None:
        qs_ped = qs_ped.filter(fecha_confirmacion__gte=inicio_dia_la_paz(filtros.fecha_desde))
    if filtros.fecha_hasta is not None:
        qs_ped = qs_ped.filter(fecha_confirmacion__lte=fin_dia_la_paz(filtros.fecha_hasta))

    pedidos_rows = (
        qs_ped.annotate(periodo=trunc_temporal("fecha_confirmacion", gran, is_datetime=True))
        .values("periodo", "proforma__moneda__codigo")
        .annotate(
            pedidos_generados=Count("id"),
            importe_no_cancelados=Coalesce(
                Sum("proforma__total", filter=~Q(estado__codigo="CANCELADO")),
                Value(CERO),
            ),
        )
        .order_by("periodo", "proforma__moneda__codigo")
    )

    pedidos_por_periodo: dict[str, int] = {}
    importes_por_moneda: dict[str, dict[str, Decimal]] = {}
    for row in pedidos_rows:
        per = formatear_periodo(row["periodo"])
        mon = row["proforma__moneda__codigo"]
        pedidos_por_periodo[per] = pedidos_por_periodo.get(per, 0) + row["pedidos_generados"]
        importes_por_moneda.setdefault(mon, {})[per] = redondear_decimal(
            row["importe_no_cancelados"]
        )

    # 3. Cobros válidos (EMITIDO sobre pedidos no cancelados) agrupados por moneda
    qs_rec = Recibo.objects.filter(estado="EMITIDO").exclude(pedido__estado__codigo="CANCELADO")
    if uid is not None:
        qs_rec = qs_rec.filter(pedido__proforma__vendedor_id=uid)
    if filtros.moneda:
        qs_rec = qs_rec.filter(pedido__proforma__moneda__codigo=filtros.moneda)
    if filtros.fecha_desde is not None:
        qs_rec = qs_rec.filter(fecha__gte=filtros.fecha_desde)
    if filtros.fecha_hasta is not None:
        qs_rec = qs_rec.filter(fecha__lte=filtros.fecha_hasta)

    cobros_rows = (
        qs_rec.annotate(periodo=trunc_temporal("fecha", gran, is_datetime=False))
        .values("periodo", "pedido__proforma__moneda__codigo")
        .annotate(cobros=Coalesce(Sum("pago_actual"), Value(CERO)))
        .order_by("periodo", "pedido__proforma__moneda__codigo")
    )
    cobros_por_moneda: dict[str, dict[str, Decimal]] = {}
    for row in cobros_rows:
        per = formatear_periodo(row["periodo"])
        mon = row["pedido__proforma__moneda__codigo"]
        cobros_por_moneda.setdefault(mon, {})[per] = redondear_decimal(row["cobros"])

    todos_periodos = sorted(
        set(serie_prof.keys())
        | set(pedidos_por_periodo.keys())
        | {p for m in importes_por_moneda.values() for p in m}
        | {p for m in cobros_por_moneda.values() for p in m}
    )
    monedas = sorted(set(importes_por_moneda.keys()) | set(cobros_por_moneda.keys()))
    if not monedas and filtros.moneda:
        monedas = [filtros.moneda]

    series_por_moneda = []
    for mon in monedas:
        puntos_mon = [
            {
                "periodo": per,
                "importe_pedidos_no_cancelados": importes_por_moneda.get(mon, {}).get(per, CERO),
                "cobros_registrados": cobros_por_moneda.get(mon, {}).get(per, CERO),
            }
            for per in todos_periodos
        ]
        series_por_moneda.append({"moneda": mon, "puntos": puntos_mon})

    return {
        "granularidad": gran,
        "puntos_conteo": [
            {
                "periodo": per,
                "proformas_formalizadas": serie_prof.get(per, 0),
                "pedidos_generados": pedidos_por_periodo.get(per, 0),
            }
            for per in todos_periodos
        ],
        "series_monetarias": series_por_moneda,
    }


def obtener_comparacion_vendedores(filtros: DashboardFilterParams) -> list[dict]:
    # Consultas separadas por entidad para evitar duplicación por JOIN.
    qs_prof = _filtrar_proformas_base(filtros, aplicar_estado_comercial=False)
    prof_rows = list(
        qs_prof.values("vendedor_id")
        .annotate(
            formalizadas=Count("id", filter=~Q(estado__codigo="BORRADOR")),
            vencidas_no_concretadas=Count(
                "id", filter=Q(estado__codigo__in=["VENCIDA", "NO_CONCRETADA"])
            ),
            vencidas=Count("id", filter=Q(estado__codigo="VENCIDA")),
            no_concretadas=Count("id", filter=Q(estado__codigo="NO_CONCRETADA")),
        )
        .order_by("vendedor_id")
    )

    formalizadas_qs = qs_prof.exclude(estado__codigo="BORRADOR")
    ped_rows = list(
        Pedido.objects.filter(proforma__in=formalizadas_qs)
        .values("proforma__vendedor_id", "proforma__moneda__codigo")
        .annotate(
            pedidos_generados=Count("id"),
            pedidos_no_cancelados=Count("id", filter=~Q(estado__codigo="CANCELADO")),
            importe_no_cancelados=Coalesce(
                Sum("proforma__total", filter=~Q(estado__codigo="CANCELADO")),
                Value(CERO),
            ),
        )
    )

    rec_qs = Recibo.objects.filter(estado="EMITIDO").exclude(pedido__estado__codigo="CANCELADO")
    if filtros.vendedor_id is not None:
        rec_qs = rec_qs.filter(pedido__proforma__vendedor_id=filtros.vendedor_id)
    if filtros.moneda:
        rec_qs = rec_qs.filter(pedido__proforma__moneda__codigo=filtros.moneda)
    if filtros.fecha_desde is not None:
        rec_qs = rec_qs.filter(pedido__proforma__fecha__gte=filtros.fecha_desde)
    if filtros.fecha_hasta is not None:
        rec_qs = rec_qs.filter(pedido__proforma__fecha__lte=filtros.fecha_hasta)

    rec_rows = list(
        rec_qs.values("pedido__proforma__vendedor_id", "pedido__proforma__moneda__codigo").annotate(
            cobros_validos=Coalesce(Sum("pago_actual"), Value(CERO))
        )
    )

    vendedor_ids = {r["vendedor_id"] for r in prof_rows}
    usuarios = {u.id: u for u in User.objects.filter(id__in=vendedor_ids)}

    ped_por_vend: dict[int, int] = {}
    mon_por_vend: dict[int, dict[str, dict[str, Decimal]]] = {}
    for r in ped_rows:
        vid = r["proforma__vendedor_id"]
        mon = r["proforma__moneda__codigo"]
        ped_por_vend[vid] = ped_por_vend.get(vid, 0) + r["pedidos_generados"]
        mon_por_vend.setdefault(vid, {})[mon] = {
            "importe": redondear_decimal(r["importe_no_cancelados"]),
            "cobros": CERO,
        }

    for r in rec_rows:
        vid = r["pedido__proforma__vendedor_id"]
        mon = r["pedido__proforma__moneda__codigo"]
        bucket = mon_por_vend.setdefault(vid, {}).setdefault(mon, {"importe": CERO, "cobros": CERO})
        bucket["cobros"] = redondear_decimal(r["cobros_validos"])

    resultados = []
    for r in prof_rows:
        vid = r["vendedor_id"]
        user = usuarios.get(vid)
        formalizadas = r["formalizadas"] or 0
        pedidos_gen = ped_por_vend.get(vid, 0)
        resumenes_moneda = []
        for mon, vals in sorted(mon_por_vend.get(vid, {}).items()):
            imp = vals["importe"]
            cob = vals["cobros"]
            resumenes_moneda.append(
                {
                    "moneda": mon,
                    "importe_pedidos_no_cancelados": imp,
                    "cobros_validos": cob,
                    "saldo_pendiente": redondear_decimal(imp - cob),
                }
            )
        resultados.append(
            {
                "vendedor_id": vid,
                "vendedor_nombre": nombre_usuario(user),
                "proformas_formalizadas": formalizadas,
                "pedidos_generados": pedidos_gen,
                "conversion_comercial": calcular_porcentaje(pedidos_gen, formalizadas),
                "vencidas_no_concretadas": r["vencidas_no_concretadas"] or 0,
                "vencidas": r["vencidas"] or 0,
                "no_concretadas": r["no_concretadas"] or 0,
                "montos_por_moneda": resumenes_moneda,
            }
        )
    return resultados


def obtener_agenda_comercial(
    filtros: DashboardFilterParams,
    *,
    vendedor_id: int,
) -> dict:
    """Agenda comercial priorizada para el encargado de tienda."""
    hoy = fecha_referencia_analitica()
    limite_7d = hoy + timedelta(days=7)

    # 1. Proformas próximas a vencer (7 días) y pendientes de revisión
    proformas_rev = (
        Proforma.objects.filter(
            vendedor_id=vendedor_id,
            estado__codigo__in=["EN_REVISION", "ENVIADA"],
        )
        .select_related("cliente", "estado", "moneda")
        .order_by("fecha", "id")
    )
    if filtros.moneda:
        proformas_rev = proformas_rev.filter(moneda__codigo=filtros.moneda)

    proximas_vencer = []
    pendientes_revision = []
    for prof in proformas_rev:
        cliente_nom = nombre_cliente_proforma(prof)
        lim = (
            fecha_limite(prof.fecha, prof.validez_oferta)
            if prof.validez_oferta and prof.validez_oferta > 0
            else None
        )
        if lim is not None and hoy <= lim <= limite_7d:
            dias_rest = (lim - hoy).days
            proximas_vencer.append(
                {
                    "tipo_documento": "PROFORMA",
                    "documento_id": prof.id,
                    "proforma_id": prof.id,
                    "pedido_id": None,
                    "numero_documento": prof.numero,
                    "cliente_nombre": cliente_nom,
                    "fecha": lim.isoformat(),
                    "estado_codigo": prof.estado.codigo,
                    "estado_nombre": prof.estado.nombre,
                    "prioridad": "ALTA" if dias_rest <= 2 else "MEDIA",
                    "categoria_agenda": "PROFORMA_PROXIMA_VENCER",
                    "dias_diferencia": dias_rest,
                }
            )
        else:
            pendientes_revision.append(
                {
                    "tipo_documento": "PROFORMA",
                    "documento_id": prof.id,
                    "proforma_id": prof.id,
                    "pedido_id": None,
                    "numero_documento": prof.numero,
                    "cliente_nombre": cliente_nom,
                    "fecha": prof.fecha.isoformat(),
                    "estado_codigo": prof.estado.codigo,
                    "estado_nombre": prof.estado.nombre,
                    "prioridad": "MEDIA",
                    "categoria_agenda": "PROFORMA_PENDIENTE_REVISION",
                    "dias_diferencia": (hoy - prof.fecha).days,
                }
            )

    # 2. Pedidos propios activos: listos para entrega, saldo pendiente, entregas próximas/retrasadas
    cobros_sq = (
        Recibo.objects.filter(pedido=OuterRef("pk"), estado="EMITIDO")
        .values("pedido")
        .annotate(s=Sum("pago_actual"))
        .values("s")[:1]
    )
    pedidos_qs = (
        Pedido.objects.filter(proforma__vendedor_id=vendedor_id)
        .exclude(estado__codigo="CANCELADO")
        .select_related("proforma__cliente", "proforma__moneda", "estado", "ordentrabajo")
        .annotate(cobrado=Coalesce(Subquery(cobros_sq), Value(CERO)))
        .order_by("id")
    )
    if filtros.moneda:
        pedidos_qs = pedidos_qs.filter(proforma__moneda__codigo=filtros.moneda)

    listos_entrega = []
    con_saldo = []
    entregas_proximas = []
    entregas_retrasadas = []

    for ped in pedidos_qs:
        prof = ped.proforma
        cliente_nom = nombre_cliente_proforma(prof)
        saldo = redondear_decimal(prof.total - ped.cobrado)
        ot = getattr(ped, "ordentrabajo", None)
        f_entrega = ot.fecha_entrega if ot else None

        if ped.estado.codigo == "LISTO_ENTREGA":
            listos_entrega.append(
                {
                    "tipo_documento": "PEDIDO",
                    "documento_id": ped.id,
                    "proforma_id": prof.id,
                    "pedido_id": ped.id,
                    "numero_documento": prof.numero,
                    "cliente_nombre": cliente_nom,
                    "fecha": (f_entrega or ped.fecha_confirmacion.date()).isoformat(),
                    "estado_codigo": ped.estado.codigo,
                    "estado_nombre": ped.estado.nombre,
                    "prioridad": "ALTA",
                    "categoria_agenda": "PEDIDO_LISTO_ENTREGA",
                    "dias_diferencia": (f_entrega - hoy).days if f_entrega else None,
                }
            )

        if saldo > CERO:
            con_saldo.append(
                {
                    "tipo_documento": "PEDIDO",
                    "documento_id": ped.id,
                    "proforma_id": prof.id,
                    "pedido_id": ped.id,
                    "numero_documento": prof.numero,
                    "cliente_nombre": cliente_nom,
                    "fecha": ped.fecha_confirmacion.date().isoformat(),
                    "estado_codigo": ped.estado.codigo,
                    "estado_nombre": ped.estado.nombre,
                    "prioridad": "ALTA" if ped.estado.codigo == "ENTREGADO" else "MEDIA",
                    "categoria_agenda": "PEDIDO_SALDO_PENDIENTE",
                    "dias_diferencia": None,
                    "moneda": prof.moneda.codigo,
                    "saldo_pendiente": saldo,
                }
            )

        if ped.estado.codigo != "ENTREGADO" and f_entrega is not None:
            diff = (f_entrega - hoy).days
            if diff < 0:
                entregas_retrasadas.append(
                    {
                        "tipo_documento": "PEDIDO",
                        "documento_id": ped.id,
                        "proforma_id": prof.id,
                        "pedido_id": ped.id,
                        "numero_documento": prof.numero,
                        "cliente_nombre": cliente_nom,
                        "fecha": f_entrega.isoformat(),
                        "estado_codigo": ped.estado.codigo,
                        "estado_nombre": ped.estado.nombre,
                        "prioridad": "CRITICA",
                        "categoria_agenda": "ENTREGA_RETRASADA",
                        "dias_diferencia": abs(diff),
                    }
                )
            elif diff <= 7:
                entregas_proximas.append(
                    {
                        "tipo_documento": "PEDIDO",
                        "documento_id": ped.id,
                        "proforma_id": prof.id,
                        "pedido_id": ped.id,
                        "numero_documento": prof.numero,
                        "cliente_nombre": cliente_nom,
                        "fecha": f_entrega.isoformat(),
                        "estado_codigo": ped.estado.codigo,
                        "estado_nombre": ped.estado.nombre,
                        "prioridad": "ALTA" if diff <= 2 else "MEDIA",
                        "categoria_agenda": "ENTREGA_PROXIMA",
                        "dias_diferencia": diff,
                    }
                )

    combinados = (
        sorted(entregas_retrasadas, key=lambda x: -(x["dias_diferencia"] or 0))
        + sorted(proximas_vencer, key=lambda x: x["dias_diferencia"] or 0)
        + listos_entrega
        + sorted(entregas_proximas, key=lambda x: x["dias_diferencia"] or 0)
        + con_saldo
        + pendientes_revision
    )

    return {
        "resumen_conteos": {
            "proformas_proximas_vencer": len(proximas_vencer),
            "proformas_pendientes_revision": len(pendientes_revision),
            "pedidos_listos_entrega": len(listos_entrega),
            "pedidos_con_saldo_pendiente": len(con_saldo),
            "entregas_proximas": len(entregas_proximas),
            "entregas_retrasadas": len(entregas_retrasadas),
        },
        "elementos": paginar_lista(combinados, filtros.page, filtros.page_size),
    }
