from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Exists, OuterRef, Q, Sum, Value
from django.db.models.functions import Coalesce

from apps.dashboard.filters import DashboardFilterParams
from apps.dashboard.services.common import (
    TZ_LA_PAZ,
    calcular_porcentaje,
    fecha_referencia_analitica,
    fin_dia_la_paz,
    formatear_periodo,
    inicio_dia_la_paz,
    nombre_cliente_proforma,
    nombre_usuario,
    paginar_lista,
    trunc_temporal,
)
from apps.ordenes_trabajo.models import HistorialEstadoOrdenTrabajo, OrdenTrabajo
from apps.proformas.models import DetalleProforma


def filtro_fabricacion_a_medida() -> Exists:
    """Subconsulta Exists para distinguir órdenes funcionales (MUEBLE_MEDIDA) de técnicas."""
    return Exists(
        DetalleProforma.objects.filter(
            proforma_id=OuterRef("pedido__proforma_id"),
            tipo_item__codigo="MUEBLE_MEDIDA",
        )
    )


def _qs_ordenes_funcionales(filtros: DashboardFilterParams, *, aplicar_estado: bool = True):
    qs = OrdenTrabajo.objects.filter(filtro_fabricacion_a_medida()).select_related(
        "estado",
        "pedido__estado",
        "pedido__proforma__cliente",
        "pedido__proforma__vendedor",
    )
    if aplicar_estado and filtros.estado_fabricacion:
        qs = qs.filter(estado__codigo=filtros.estado_fabricacion)
    if filtros.tipo_mueble:
        qs = qs.filter(
            Exists(
                DetalleProforma.objects.filter(
                    proforma_id=OuterRef("pedido__proforma_id"),
                    tipo_item__codigo="MUEBLE_MEDIDA",
                    especificacionmueble__tipo_mueble__codigo=filtros.tipo_mueble,
                )
            )
        )
    if filtros.entrega_desde is not None:
        qs = qs.filter(fecha_entrega__gte=filtros.entrega_desde)
    if filtros.entrega_hasta is not None:
        qs = qs.filter(fecha_entrega__lte=filtros.entrega_hasta)
    return qs


def _duracion_y_antiguedad_desde_historial(ordenes_qs) -> dict:
    """Calcula duración promedio de terminadas y antigüedad de activas con transiciones reales."""
    hoy = fecha_referencia_analitica()
    terminadas_ids = list(
        ordenes_qs.filter(estado__codigo="TERMINADA").values_list("id", flat=True)
    )
    activas = list(ordenes_qs.filter(estado__codigo="EN_PROCESO").values("id", "fecha_inicio"))

    duraciones_horas: list[float] = []
    if terminadas_ids:
        hist_term = (
            HistorialEstadoOrdenTrabajo.objects.filter(
                orden_trabajo_id__in=terminadas_ids,
                estado_nuevo__codigo__in=["EN_PROCESO", "TERMINADA"],
            )
            .values("orden_trabajo_id", "estado_nuevo__codigo", "fecha")
            .order_by("orden_trabajo_id", "fecha", "id")
        )
        tiempos_ot: dict[int, dict[str, object]] = {}
        for h in hist_term:
            bucket = tiempos_ot.setdefault(h["orden_trabajo_id"], {})
            codigo = h["estado_nuevo__codigo"]
            if codigo not in bucket:
                bucket[codigo] = h["fecha"]
        for bucket in tiempos_ot.values():
            ini = bucket.get("EN_PROCESO")
            fin = bucket.get("TERMINADA")
            if ini is not None and fin is not None and fin >= ini:
                duraciones_horas.append((fin - ini).total_seconds() / 3600.0)

    antiguedad_dias: list[int] = []
    if activas:
        act_ids = [a["id"] for a in activas]
        hist_act = (
            HistorialEstadoOrdenTrabajo.objects.filter(
                orden_trabajo_id__in=act_ids,
                estado_nuevo__codigo="EN_PROCESO",
            )
            .values("orden_trabajo_id", "fecha")
            .order_by("orden_trabajo_id", "fecha", "id")
        )
        inicio_hist: dict[int, object] = {}
        for h in hist_act:
            inicio_hist.setdefault(h["orden_trabajo_id"], h["fecha"])
        for a in activas:
            ts = inicio_hist.get(a["id"])
            if ts is not None:
                f_ini = ts.astimezone(TZ_LA_PAZ).date()
                antiguedad_dias.append(max(0, (hoy - f_ini).days))
            elif a["fecha_inicio"] is not None:
                antiguedad_dias.append(max(0, (hoy - a["fecha_inicio"]).days))

    promedio_horas = (
        round(sum(duraciones_horas) / len(duraciones_horas), 2) if duraciones_horas else None
    )
    promedio_dias = round(promedio_horas / 24.0, 2) if promedio_horas is not None else None
    antiguedad_prom = (
        round(sum(antiguedad_dias) / len(antiguedad_dias), 2) if antiguedad_dias else None
    )
    antiguedad_max = max(antiguedad_dias) if antiguedad_dias else None

    return {
        "tiempo_promedio_fabricacion_horas": promedio_horas,
        "tiempo_promedio_fabricacion_dias": promedio_dias,
        "ordenes_con_duracion_medible": len(duraciones_horas),
        "antiguedad_promedio_activas_dias": antiguedad_prom,
        "antiguedad_maxima_activas_dias": antiguedad_max,
    }


def _metricas_entrega_y_cumplimiento(ordenes_qs, filtros: DashboardFilterParams) -> dict:
    hoy = fecha_referencia_analitica()
    limite_7d = hoy + timedelta(days=7)

    pendientes_entrega = ordenes_qs.exclude(estado__codigo="CANCELADA").exclude(
        pedido__estado__codigo="ENTREGADO"
    )
    entregas_proximas = pendientes_entrega.filter(
        fecha_entrega__gte=hoy, fecha_entrega__lte=limite_7d
    ).count()
    entregas_retrasadas = pendientes_entrega.filter(fecha_entrega__lt=hoy).count()

    qs_efectivas = ordenes_qs.filter(pedido__fecha_entrega_efectiva__isnull=False)
    if filtros.fecha_desde is not None:
        qs_efectivas = qs_efectivas.filter(pedido__fecha_entrega_efectiva__gte=filtros.fecha_desde)
    if filtros.fecha_hasta is not None:
        qs_efectivas = qs_efectivas.filter(pedido__fecha_entrega_efectiva__lte=filtros.fecha_hasta)
    entregas_efectivas = qs_efectivas.count()

    evaluables = qs_efectivas.filter(fecha_entrega__isnull=False)
    total_eval = evaluables.count()
    en_plazo = sum(
        1
        for f_eff, f_prog in evaluables.values_list(
            "pedido__fecha_entrega_efectiva", "fecha_entrega"
        )
        if f_eff <= f_prog
    )
    cumplimiento = calcular_porcentaje(en_plazo, total_eval)

    return {
        "entregas_proximas": entregas_proximas,
        "entregas_retrasadas": entregas_retrasadas,
        "entregas_efectivas": entregas_efectivas,
        "entregas_evaluables_plazo": total_eval,
        "entregas_en_plazo": en_plazo,
        "cumplimiento_entregas_porcentaje": cumplimiento,
    }


def obtener_resumen_produccion_admin(filtros: DashboardFilterParams) -> dict:
    """Resumen de producción y logística para el dashboard del administrador."""
    qs_func = _qs_ordenes_funcionales(filtros)
    if filtros.vendedor_id is not None:
        qs_func = qs_func.filter(pedido__proforma__vendedor_id=filtros.vendedor_id)
    if filtros.fecha_desde is not None:
        qs_func = qs_func.filter(fecha__gte=filtros.fecha_desde)
    if filtros.fecha_hasta is not None:
        qs_func = qs_func.filter(fecha__lte=filtros.fecha_hasta)

    por_estado_func = [
        {
            "codigo": r["estado__codigo"],
            "nombre": r["estado__nombre"],
            "cantidad": r["cantidad"],
        }
        for r in qs_func.values("estado__codigo", "estado__nombre")
        .annotate(cantidad=Count("id"))
        .order_by("estado__codigo")
    ]

    qs_tec = OrdenTrabajo.objects.filter(~filtro_fabricacion_a_medida())
    if filtros.vendedor_id is not None:
        qs_tec = qs_tec.filter(pedido__proforma__vendedor_id=filtros.vendedor_id)
    if filtros.fecha_desde is not None:
        qs_tec = qs_tec.filter(fecha__gte=filtros.fecha_desde)
    if filtros.fecha_hasta is not None:
        qs_tec = qs_tec.filter(fecha__lte=filtros.fecha_hasta)

    por_estado_tec = [
        {
            "codigo": r["estado__codigo"],
            "nombre": r["estado__nombre"],
            "cantidad": r["cantidad"],
        }
        for r in qs_tec.values("estado__codigo", "estado__nombre")
        .annotate(cantidad=Count("id"))
        .order_by("estado__codigo")
    ]

    fabricaciones_activas = qs_func.filter(estado__codigo="EN_PROCESO").count()
    entregas = _metricas_entrega_y_cumplimiento(qs_func, filtros)

    return {
        "ordenes_fabricacion_total": sum(x["cantidad"] for x in por_estado_func),
        "ordenes_fabricacion_por_estado": por_estado_func,
        "ordenes_tecnicas_total": sum(x["cantidad"] for x in por_estado_tec),
        "ordenes_tecnicas_por_estado": por_estado_tec,
        "fabricaciones_activas": fabricaciones_activas,
        **entregas,
    }


def obtener_dashboard_taller(filtros: DashboardFilterParams) -> dict:
    """Indicadores operativos de taller (exclusivamente fabricación a medida, sin montos)."""
    qs_func = _qs_ordenes_funcionales(filtros)

    conteos = qs_func.aggregate(
        pendientes=Count("id", filter=Q(estado__codigo="PENDIENTE")),
        en_proceso=Count("id", filter=Q(estado__codigo="EN_PROCESO")),
        terminadas=Count("id", filter=Q(estado__codigo="TERMINADA")),
        canceladas=Count("id", filter=Q(estado__codigo="CANCELADA")),
    )
    pendientes = conteos["pendientes"] or 0
    en_proceso = conteos["en_proceso"] or 0
    terminadas = conteos["terminadas"] or 0
    canceladas = conteos["canceladas"] or 0

    hist_qs = HistorialEstadoOrdenTrabajo.objects.filter(
        orden_trabajo__in=qs_func,
        estado_nuevo__codigo__in=["EN_PROCESO", "TERMINADA"],
    )
    if filtros.fecha_desde is not None:
        hist_qs = hist_qs.filter(fecha__gte=inicio_dia_la_paz(filtros.fecha_desde))
    if filtros.fecha_hasta is not None:
        hist_qs = hist_qs.filter(fecha__lte=fin_dia_la_paz(filtros.fecha_hasta))

    trans_counts = hist_qs.aggregate(
        iniciadas=Count(
            "orden_trabajo_id", filter=Q(estado_nuevo__codigo="EN_PROCESO"), distinct=True
        ),
        terminadas=Count(
            "orden_trabajo_id", filter=Q(estado_nuevo__codigo="TERMINADA"), distinct=True
        ),
    )

    tiempos = _duracion_y_antiguedad_desde_historial(qs_func)
    entregas = _metricas_entrega_y_cumplimiento(qs_func, filtros)

    return {
        "pendientes": pendientes,
        "en_proceso": en_proceso,
        "terminadas": terminadas,
        "canceladas": canceladas,
        "carga_activa_fabricacion": pendientes + en_proceso,
        "fabricaciones_iniciadas_periodo": trans_counts["iniciadas"] or 0,
        "fabricaciones_terminadas_periodo": trans_counts["terminadas"] or 0,
        **tiempos,
        **entregas,
    }


def obtener_cola_prioridades_taller(filtros: DashboardFilterParams) -> dict:
    """Cola priorizada sin duplicaciones: cada OT se asigna a su categoría más urgente."""
    hoy = fecha_referencia_analitica()
    limite_7d = hoy + timedelta(days=7)

    qs_func = (
        _qs_ordenes_funcionales(filtros)
        .exclude(estado__codigo="CANCELADA")
        .prefetch_related(
            "pedido__proforma__detalles__tipo_item",
            "pedido__proforma__detalles__especificacionmueble__tipo_mueble",
        )
        .order_by("fecha_entrega", "id")
    )

    prioridad_orden = {
        "ENTREGA_VENCIDA": 1,
        "ENTREGA_PROXIMA": 2,
        "PENDIENTE_INICIAR": 3,
        "TERMINADA_PENDIENTE_AUTORIZACION": 4,
        "SIN_FECHA_ENTREGA": 5,
    }

    items = []
    for ot in qs_func:
        ped_estado = ot.pedido.estado.codigo
        ot_estado = ot.estado.codigo
        f_ent = ot.fecha_entrega

        if ped_estado == "ENTREGADO":
            continue

        categoria = None
        dias_diff: int | None = None
        if f_ent is not None and f_ent < hoy:
            categoria = "ENTREGA_VENCIDA"
            dias_diff = (f_ent - hoy).days  # negativo = días de retraso
        elif f_ent is not None and hoy <= f_ent <= limite_7d:
            categoria = "ENTREGA_PROXIMA"
            dias_diff = (f_ent - hoy).days
        elif ot_estado == "PENDIENTE":
            categoria = "PENDIENTE_INICIAR"
            dias_diff = (f_ent - hoy).days if f_ent is not None else None
        elif ot_estado == "TERMINADA":
            categoria = "TERMINADA_PENDIENTE_AUTORIZACION"
            dias_diff = (f_ent - hoy).days if f_ent is not None else None
        elif f_ent is None and ot_estado in {"PENDIENTE", "EN_PROCESO"}:
            categoria = "SIN_FECHA_ENTREGA"
            dias_diff = None

        if categoria is None:
            continue

        muebles = []
        for det in ot.pedido.proforma.detalles.all():
            if det.tipo_item.codigo != "MUEBLE_MEDIDA":
                continue
            spec = getattr(det, "especificacionmueble", None)
            tipo_nom = spec.tipo_mueble.nombre if spec and spec.tipo_mueble else None
            muebles.append(
                {
                    "nombre": det.nombre,
                    "tipo_mueble": tipo_nom,
                    "cantidad": det.cantidad,
                }
            )

        items.append(
            {
                "orden_trabajo_id": ot.id,
                "numero_ot": ot.numero,
                "cliente_nombre": nombre_cliente_proforma(ot.pedido.proforma),
                "vendedor_nombre": nombre_usuario(ot.pedido.proforma.vendedor),
                "muebles_solicitados": muebles,
                "estado_codigo": ot_estado,
                "estado_nombre": ot.estado.nombre,
                "pedido_estado_codigo": ped_estado,
                "fecha_prevista": f_ent.isoformat() if f_ent else None,
                "dias_diferencia": dias_diff,
                "categoria_prioridad": categoria,
                "_rank": prioridad_orden[categoria],
            }
        )

    items.sort(
        key=lambda x: (
            x["_rank"],
            x["dias_diferencia"] if x["dias_diferencia"] is not None else 999999,
            x["numero_ot"],
        )
    )
    for item in items:
        item.pop("_rank", None)

    return paginar_lista(items, filtros.page, filtros.page_size)


def obtener_planificacion_taller(filtros: DashboardFilterParams) -> dict:
    """Calendario de planificación y análisis de fabricación para el jefe de taller."""
    qs_func = _qs_ordenes_funcionales(filtros)

    # Eventos efectivos de inicio y fin desde historial (con respaldo en fecha_inicio / fecha_fin)
    hist_qs = HistorialEstadoOrdenTrabajo.objects.filter(
        orden_trabajo__in=qs_func,
        estado_nuevo__codigo__in=["EN_PROCESO", "TERMINADA"],
    ).select_related(
        "estado_nuevo",
        "orden_trabajo__pedido__proforma__cliente",
        "orden_trabajo__estado",
    )

    if filtros.fecha_desde is not None:
        hist_qs = hist_qs.filter(fecha__gte=inicio_dia_la_paz(filtros.fecha_desde))
    if filtros.fecha_hasta is not None:
        hist_qs = hist_qs.filter(fecha__lte=fin_dia_la_paz(filtros.fecha_hasta))

    eventos = []
    for h in hist_qs.order_by("fecha", "id"):
        ot = h.orden_trabajo
        tipo_ev = (
            "INICIO_FABRICACION" if h.estado_nuevo.codigo == "EN_PROCESO" else "FIN_FABRICACION"
        )
        eventos.append(
            {
                "orden_trabajo_id": ot.id,
                "numero_ot": ot.numero,
                "tipo_evento": tipo_ev,
                "naturaleza": "EFECTIVA",
                "fecha": h.fecha.astimezone(TZ_LA_PAZ).date().isoformat(),
                "fecha_hora": h.fecha.astimezone(TZ_LA_PAZ).isoformat(),
                "cliente_nombre": nombre_cliente_proforma(ot.pedido.proforma),
                "estado_codigo": ot.estado.codigo,
            }
        )

    # Entregas previstas (PLANIFICADA) y entregas efectivas (EFECTIVA)
    for ot in qs_func.order_by("fecha_entrega", "id"):
        cli = nombre_cliente_proforma(ot.pedido.proforma)
        if ot.fecha_entrega is not None:
            incluir = True
            if filtros.fecha_desde and ot.fecha_entrega < filtros.fecha_desde:
                incluir = False
            if filtros.fecha_hasta and ot.fecha_entrega > filtros.fecha_hasta:
                incluir = False
            if incluir:
                eventos.append(
                    {
                        "orden_trabajo_id": ot.id,
                        "numero_ot": ot.numero,
                        "tipo_evento": "ENTREGA_PREVISTA",
                        "naturaleza": "PLANIFICADA",
                        "fecha": ot.fecha_entrega.isoformat(),
                        "fecha_hora": None,
                        "cliente_nombre": cli,
                        "estado_codigo": ot.estado.codigo,
                    }
                )
        f_eff = ot.pedido.fecha_entrega_efectiva
        if f_eff is not None:
            incluir_eff = True
            if filtros.fecha_desde and f_eff < filtros.fecha_desde:
                incluir_eff = False
            if filtros.fecha_hasta and f_eff > filtros.fecha_hasta:
                incluir_eff = False
            if incluir_eff:
                eventos.append(
                    {
                        "orden_trabajo_id": ot.id,
                        "numero_ot": ot.numero,
                        "tipo_evento": "ENTREGA_EFECTIVA",
                        "naturaleza": "EFECTIVA",
                        "fecha": f_eff.isoformat(),
                        "fecha_hora": None,
                        "cliente_nombre": cli,
                        "estado_codigo": ot.estado.codigo,
                    }
                )

    eventos.sort(key=lambda e: (e["fecha"], e["numero_ot"], e["tipo_evento"]))

    # Análisis de fabricación: evolución de iniciadas y terminadas
    evo_rows = (
        hist_qs.annotate(periodo=trunc_temporal("fecha", filtros.granularidad, is_datetime=True))
        .values("periodo")
        .annotate(
            iniciadas=Count(
                "orden_trabajo_id", filter=Q(estado_nuevo__codigo="EN_PROCESO"), distinct=True
            ),
            terminadas=Count(
                "orden_trabajo_id", filter=Q(estado_nuevo__codigo="TERMINADA"), distinct=True
            ),
        )
        .order_by("periodo")
    )
    evolucion_fabricaciones = [
        {
            "periodo": formatear_periodo(r["periodo"]),
            "iniciadas": r["iniciadas"],
            "terminadas": r["terminadas"],
        }
        for r in evo_rows
    ]

    # Cantidades de muebles fabricados (OT TERMINADA) agrupadas por tipo
    det_qs = DetalleProforma.objects.filter(
        tipo_item__codigo="MUEBLE_MEDIDA",
        proforma__pedido__ordentrabajo__in=qs_func.filter(estado__codigo="TERMINADA"),
    )
    if filtros.tipo_mueble:
        det_qs = det_qs.filter(especificacionmueble__tipo_mueble__codigo=filtros.tipo_mueble)

    muebles_por_tipo = [
        {
            "tipo_mueble_codigo": r["especificacionmueble__tipo_mueble__codigo"] or "SIN_TIPO",
            "tipo_mueble_nombre": (
                r["especificacionmueble__tipo_mueble__nombre"] or "Sin especificar"
            ),
            "cantidad_fabricada": Decimal(str(r["cantidad_fabricada"])),
            "ordenes_count": r["ordenes_count"],
        }
        for r in det_qs.values(
            "especificacionmueble__tipo_mueble__codigo",
            "especificacionmueble__tipo_mueble__nombre",
        )
        .annotate(
            cantidad_fabricada=Coalesce(Sum("cantidad"), Value(Decimal("0.0000"))),
            ordenes_count=Count("proforma__pedido__ordentrabajo", distinct=True),
        )
        .order_by("-cantidad_fabricada")
    ]

    distribucion_estados = [
        {
            "codigo": r["estado__codigo"],
            "nombre": r["estado__nombre"],
            "cantidad": r["cantidad"],
        }
        for r in qs_func.values("estado__codigo", "estado__nombre")
        .annotate(cantidad=Count("id"))
        .order_by("estado__codigo")
    ]

    tiempos = _duracion_y_antiguedad_desde_historial(qs_func)

    return {
        "calendario_eventos": paginar_lista(eventos, filtros.page, filtros.page_size),
        "analisis_fabricacion": {
            "granularidad": filtros.granularidad,
            "evolucion_fabricaciones": evolucion_fabricaciones,
            "duracion_promedio_horas": tiempos["tiempo_promedio_fabricacion_horas"],
            "duracion_promedio_dias": tiempos["tiempo_promedio_fabricacion_dias"],
            "ordenes_con_duracion_medible": tiempos["ordenes_con_duracion_medible"],
            "muebles_fabricados_por_tipo": muebles_por_tipo,
            "distribucion_ordenes_estado": distribucion_estados,
        },
    }
