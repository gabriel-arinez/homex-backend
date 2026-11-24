"""Auditoría individual, por cohorte, temporal y de conciliación contra oráculos."""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from apps.catalogo.models import Producto
from apps.clientes.models import Cliente
from apps.movimientos_stock.models import MovimientoStock
from apps.notas_entrega.models import NotaEntrega
from apps.ordenes_trabajo.models import OrdenTrabajo
from apps.pedidos.models import Pedido
from apps.proformas.importador_homex.validacion import (
    ResultadoValidacionEscenario,
    parsear_decimal,
    parsear_fecha,
)
from apps.proformas.models import Proforma
from apps.recibos.models import Recibo

NAMESPACE_HOMEX = uuid.UUID("7f3b9c1a-4d2e-4f8a-9b1c-202611240001")
MARCADOR_ESCENARIO = "perfil=ESCENARIO"
MARCADOR_DOCUMENTAL = "perfil=DOCUMENTAL"


def clave_idempotencia_escenario(entidad: str, source_id: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE_HOMEX, f"ESCENARIO:{entidad}:{source_id}")


def _formatear_cantidad(valor: Decimal) -> str:
    if valor == valor.to_integral_value():
        return str(valor.quantize(Decimal("1")))
    return format(valor.normalize(), "f")


def _extraer_source_id_cliente(observaciones: str | None) -> str | None:
    if not observaciones or "source_id=" not in observaciones:
        return None
    for token in observaciones.split():
        if token.startswith("source_id="):
            return token.split("=", 1)[1]
    return None


def _proyectar_estado_al_corte(
    validacion: ResultadoValidacionEscenario,
    *,
    fecha_corte: date,
) -> dict:
    """Proyecta el estado exacto esperado de todas las entidades a fecha_corte."""
    catalogo_por_sku = {p["sku"]: p for p in validacion.catalogo}
    proformas_por_id = {p["id"]: p for p in validacion.proformas}
    recibos_por_id = {r["id"]: r for r in validacion.recibos_objetivo}
    stock_por_sku = {
        p["sku"]: parsear_decimal(p["stock_inicial"], f"{p['sku']}.stock_inicial")
        for p in validacion.catalogo
    }

    proformas_esp: dict[str, dict] = {}
    pedidos_esp: dict[str, dict] = {}
    ots_esp: dict[str, dict] = {}
    recibos_esp: dict[str, dict] = {}
    notas_esp: dict[str, str] = {}
    movimientos_venta_esp = 0
    movimientos_reversa_esp = 0
    acumulado_por_pedido: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))

    for ev in validacion.eventos:
        fecha_ev = parsear_fecha(ev["fecha"], f"{ev['id']}.fecha")
        if fecha_ev > fecha_corte:
            continue
        tipo = ev["tipo"]
        pf_id = ev["proforma_id"]
        pf_data = proformas_por_id[pf_id]

        if tipo == "CREAR_BORRADOR":
            proformas_esp[pf_id] = {"estado": "BORRADOR", "data": pf_data}
        elif tipo == "ENVIAR_PROFORMA":
            proformas_esp[pf_id]["estado"] = "EN_REVISION"
        elif tipo == "ANULAR_PROFORMA":
            proformas_esp[pf_id]["estado"] = "ANULADA"
        elif tipo == "MARCAR_NO_CONCRETADA":
            proformas_esp[pf_id]["estado"] = "NO_CONCRETADA"
        elif tipo == "VENCER_PROFORMA":
            proformas_esp[pf_id]["estado"] = "VENCIDA"
        elif tipo == "APROBAR_PROFORMA":
            proformas_esp[pf_id]["estado"] = "APROBADA"
            ped_id = ev["pedido_id"]
            tiene_muebles = any(
                linea.get("tipo_item") == "MUEBLE_MEDIDA" for linea in pf_data["lineas"]
            )
            pedidos_esp[ped_id] = {
                "proforma_id": pf_id,
                "estado": "CONFIRMADO",
                "fecha_confirmacion": ev["fecha"],
                "fecha_entrega_simulada": None,
                "total": parsear_decimal(pf_data["total"], f"{pf_id}.total"),
                "vendedor": pf_data["vendedor"],
                "mes_cohorte": pf_data.get("mes_cohorte") or pf_data["fecha"][:7],
                "tiene_muebles": tiene_muebles,
            }
            ots_esp[ped_id] = {"estado": "PENDIENTE", "tiene_muebles": tiene_muebles}
            for linea in pf_data["lineas"]:
                sku = linea.get("sku")
                if sku and catalogo_por_sku[sku]["modalidad_abastecimiento"] == "CON_STOCK":
                    cant = parsear_decimal(linea["cantidad"], f"{pf_id}.cantidad")
                    stock_por_sku[sku] -= cant
                    movimientos_venta_esp += 1
        elif tipo == "EMITIR_RECIBO":
            rec_id = ev["recibo_id"]
            rec_data = recibos_por_id[rec_id]
            ped_id = ev["pedido_id"]
            pago = parsear_decimal(rec_data["pago_actual"], f"{rec_id}.pago_actual")
            acumulado_por_pedido[ped_id] += pago
            recibos_esp[rec_id] = {
                **rec_data,
                "a_cuenta_corte": acumulado_por_pedido[ped_id],
                "saldo_corte": pedidos_esp[ped_id]["total"] - acumulado_por_pedido[ped_id],
            }
        elif tipo == "EN_PRODUCCION":
            ped_id = ev["pedido_id"]
            pedidos_esp[ped_id]["estado"] = "EN_PRODUCCION"
            ots_esp[ped_id]["estado"] = "EN_PROCESO"
        elif tipo == "LISTO_ENTREGA":
            ped_id = ev["pedido_id"]
            pedidos_esp[ped_id]["estado"] = "LISTO_ENTREGA"
            ots_esp[ped_id]["estado"] = "TERMINADA"
            if ped_id not in notas_esp:
                notas_esp[ped_id] = ev["fecha"]
        elif tipo == "ENTREGADO":
            ped_id = ev["pedido_id"]
            pedidos_esp[ped_id]["estado"] = "ENTREGADO"
            pedidos_esp[ped_id]["fecha_entrega_simulada"] = ev["fecha"]
        elif tipo == "CANCELAR_PEDIDO":
            ped_id = ev["pedido_id"]
            pedidos_esp[ped_id]["estado"] = "CANCELADO"
            ots_esp[ped_id]["estado"] = "CANCELADA"
            for linea in pf_data["lineas"]:
                sku = linea.get("sku")
                if sku and catalogo_por_sku[sku]["modalidad_abastecimiento"] == "CON_STOCK":
                    cant = parsear_decimal(linea["cantidad"], f"{pf_id}.cantidad")
                    stock_por_sku[sku] += cant
                    movimientos_reversa_esp += 1

    return {
        "proformas": proformas_esp,
        "pedidos": pedidos_esp,
        "ots": ots_esp,
        "recibos": recibos_esp,
        "notas": notas_esp,
        "movimientos_venta": movimientos_venta_esp,
        "movimientos_reversa": movimientos_reversa_esp,
        "stock_por_sku": stock_por_sku,
    }


def auditar_escenario(
    validacion: ResultadoValidacionEscenario,
    *,
    fecha_corte: date,
) -> dict:
    """Contrasta registros individuales, cohortes y totales contra oráculos al corte."""
    corte_completo = fecha_corte >= date.fromisoformat(
        validacion.resumen_validacion["corte_virtual"]
    )
    proyeccion = _proyectar_estado_al_corte(validacion, fecha_corte=fecha_corte)
    tz_local = ZoneInfo(settings.TIME_ZONE)

    skus_escenario = [p["sku"] for p in validacion.catalogo]
    productos_qs = Producto.objects.filter(sku__in=skus_escenario)
    productos_por_sku = {p.sku: p for p in productos_qs}

    clientes_qs = Cliente.objects.filter(observaciones__contains=MARCADOR_ESCENARIO)
    clientes_source_por_pk = {
        c.pk: _extraer_source_id_cliente(c.observaciones) for c in clientes_qs
    }

    claves_pf = {
        clave_idempotencia_escenario("PROFORMA", pf["id"]): pf["id"] for pf in validacion.proformas
    }
    proformas_qs = (
        Proforma.objects.filter(clave_idempotencia__in=claves_pf.keys())
        .select_related("estado", "vendedor", "moneda", "cliente")
        .prefetch_related(
            "detalles__producto", "detalles__tipo_item", "detalles__especificacionmueble"
        )
    )
    proformas_por_id_fuente = {claves_pf[p.clave_idempotencia]: p for p in proformas_qs}

    pedidos_qs = Pedido.objects.filter(proforma__in=proformas_qs).select_related(
        "estado", "proforma", "proforma__vendedor"
    )
    pedidos_por_pf_fuente = {claves_pf[p.proforma.clave_idempotencia]: p for p in pedidos_qs}
    ots_qs = OrdenTrabajo.objects.filter(pedido__in=pedidos_qs).select_related(
        "estado", "jefe_taller", "pedido__proforma"
    )
    ots_por_pedido_id = {ot.pedido_id: ot for ot in ots_qs}

    claves_rec = {
        clave_idempotencia_escenario("RECIBO", r["id"]): r["id"]
        for r in validacion.recibos_objetivo
    }
    recibos_qs = Recibo.objects.filter(pedido__in=pedidos_qs, estado="EMITIDO").select_related(
        "tipo_pago", "created_by", "pedido__proforma"
    )
    recibos_por_id_fuente = {
        claves_rec[r.clave_idempotencia]: r
        for r in recibos_qs
        if r.clave_idempotencia in claves_rec
    }

    notas_qs = NotaEntrega.objects.filter(pedido__in=pedidos_qs).select_related(
        "vendedor", "pedido__proforma"
    )
    notas_por_pedido_id = {n.pedido_id: n for n in notas_qs}

    movs_qs = MovimientoStock.objects.filter(producto__in=productos_qs).select_related(
        "tipo_movimiento", "producto", "movimiento_referencia"
    )

    ots_funcionales = []
    ots_tecnicas = []
    for ot in ots_qs:
        tiene_muebles = ot.pedido.proforma.detalles.filter(
            tipo_item__concepto__codigo="TIPO_ITEM",
            tipo_item__codigo="MUEBLE_MEDIDA",
        ).exists()
        if tiene_muebles:
            ots_funcionales.append(ot)
        else:
            ots_tecnicas.append(ot)

    stock_negativo = [{"sku": p.sku, "stock": str(p.stock)} for p in productos_qs if p.stock < 0]
    bajo_pedido_con_stock = [
        {"sku": p.sku, "stock": str(p.stock)}
        for p in productos_qs
        if p.modalidad_abastecimiento == Producto.MODALIDAD_BAJO_PEDIDO and p.stock != 0
    ]

    movs_por_tipo = Counter(m.tipo_movimiento.codigo for m in movs_qs)
    duplicados_mov_pedido = (
        movs_qs.filter(pedido__isnull=False)
        .values("pedido_id", "producto_id", "tipo_movimiento__codigo")
        .annotate(c=Sum("cantidad"))
    )
    ventas_dup = movs_qs.filter(tipo_movimiento__codigo="VENTA", pedido__isnull=False).values(
        "pedido_id", "producto_id"
    )
    conteo_ventas = Counter((v["pedido_id"], v["producto_id"]) for v in ventas_dup)
    movimientos_venta_duplicados = [
        {"pedido_id": k[0], "producto_id": k[1], "cantidad_registros": v}
        for k, v in conteo_ventas.items()
        if v > 1
    ]

    stock_inicial_total = sum(
        (m.cantidad for m in movs_qs if m.tipo_movimiento.codigo == "CARGA_INICIAL"),
        Decimal("0"),
    )
    stock_final_total = sum((p.stock for p in productos_qs), Decimal("0"))
    importe_no_cancelados = sum(
        (p.proforma.total for p in pedidos_qs if p.estado.codigo != "CANCELADO"),
        Decimal("0.00"),
    )
    pagos_totales = sum((r.pago_actual for r in recibos_qs), Decimal("0.00"))
    saldo_pendiente = importe_no_cancelados - pagos_totales

    estados_proforma = Counter(p.estado.codigo for p in proformas_qs)
    formalizadas = sum(1 for p in proformas_qs if p.estado.codigo != "BORRADOR")
    borradores = estados_proforma.get("BORRADOR", 0)
    estados_pedido = Counter(p.estado.codigo for p in pedidos_qs)
    estados_ot_funcionales = Counter(ot.estado.codigo for ot in ots_funcionales)

    discrepancias: list[str] = []
    if stock_negativo:
        discrepancias.append(f"Existencias negativas detectadas: {stock_negativo}")
    if bajo_pedido_con_stock:
        discrepancias.append(f"Productos BAJO_PEDIDO con stock != 0: {bajo_pedido_con_stock}")
    if movimientos_venta_duplicados:
        discrepancias.append(f"Movimientos VENTA duplicados: {movimientos_venta_duplicados}")

    doc_mezclado = Producto.objects.filter(
        sku__in=skus_escenario, observaciones__contains=MARCADOR_DOCUMENTAL
    ).exists()
    if doc_mezclado:
        discrepancias.append("Se detectó mezcla de marcadores documentales en productos simulados.")

    # Auditoría individual al corte (aplica tanto a cortes parciales como al corte final)
    if clientes_qs.count() != len(validacion.clientes):
        discrepancias.append(
            f"clientes: real={clientes_qs.count()} != esperado={len(validacion.clientes)}"
        )
    if productos_qs.count() != len(validacion.catalogo):
        discrepancias.append(
            f"productos: real={productos_qs.count()} != esperado={len(validacion.catalogo)}"
        )

    pfs_esp = proyeccion["proformas"]
    if proformas_qs.count() != len(pfs_esp):
        discrepancias.append(
            f"proformas al corte {fecha_corte}: real={proformas_qs.count()} != {len(pfs_esp)}"
        )
    for pf_id, esp in pfs_esp.items():
        pf_obj = proformas_por_id_fuente.get(pf_id)
        if pf_obj is None:
            discrepancias.append(f"Falta proforma {pf_id} al corte {fecha_corte}.")
            continue
        pf_data = esp["data"]
        if pf_obj.estado.codigo != esp["estado"]:
            discrepancias.append(
                f"Proforma {pf_id} estado {pf_obj.estado.codigo} != {esp['estado']}"
            )
        if pf_obj.fecha != parsear_fecha(pf_data["fecha"], f"{pf_id}.fecha"):
            discrepancias.append(f"Proforma {pf_id} fecha {pf_obj.fecha} != {pf_data['fecha']}")
        if pf_obj.vendedor.username != pf_data["vendedor"]:
            discrepancias.append(
                f"Proforma {pf_id} vendedor {pf_obj.vendedor.username} != {pf_data['vendedor']}"
            )
        if clientes_source_por_pk.get(pf_obj.cliente_id) != pf_data["cliente_id"]:
            discrepancias.append(
                f"Proforma {pf_id} cliente {clientes_source_por_pk.get(pf_obj.cliente_id)} "
                f"!= {pf_data['cliente_id']}"
            )
        if pf_obj.total != parsear_decimal(pf_data["total"], f"{pf_id}.total"):
            discrepancias.append(f"Proforma {pf_id} total {pf_obj.total} != {pf_data['total']}")
        detalles = list(pf_obj.detalles.order_by("id"))
        if len(detalles) != len(pf_data["lineas"]):
            discrepancias.append(
                f"Proforma {pf_id} detalles {len(detalles)} != {len(pf_data['lineas'])}"
            )
        else:
            for det, l_esp in zip(detalles, pf_data["lineas"], strict=True):
                sku_real = det.producto.sku if det.producto else None
                if sku_real != l_esp.get("sku") or det.total != parsear_decimal(
                    l_esp["total"], f"{pf_id}.linea.total"
                ):
                    discrepancias.append(f"Proforma {pf_id} detalle inconsistente ({sku_real}).")
                if l_esp.get("tipo_item") == "MUEBLE_MEDIDA" and not hasattr(
                    det, "especificacionmueble"
                ):
                    discrepancias.append(f"Proforma {pf_id} mueble sin especificación.")

    peds_esp = proyeccion["pedidos"]
    if pedidos_qs.count() != len(peds_esp):
        discrepancias.append(
            f"pedidos al corte {fecha_corte}: real={pedidos_qs.count()} != {len(peds_esp)}"
        )
    pedidos_obj_por_id = {p["id"]: p for p in validacion.pedidos_objetivo}
    ots_obj_por_ped = {o["pedido_id"]: o for o in validacion.ordenes_trabajo_objetivo}

    for ped_id, esp in peds_esp.items():
        ped_obj = pedidos_por_pf_fuente.get(esp["proforma_id"])
        if ped_obj is None:
            discrepancias.append(f"Falta pedido {ped_id} ({esp['proforma_id']}).")
            continue
        if ped_obj.estado.codigo != esp["estado"]:
            discrepancias.append(
                f"Pedido {ped_id} estado {ped_obj.estado.codigo} != {esp['estado']}"
            )
        fecha_conf_local = timezone.localtime(ped_obj.fecha_confirmacion, tz_local).date()
        if fecha_conf_local != parsear_fecha(esp["fecha_confirmacion"], f"{ped_id}.fecha_conf"):
            discrepancias.append(
                f"Pedido {ped_id} fecha_confirmacion {fecha_conf_local} "
                f"!= {esp['fecha_confirmacion']}"
            )
        ot = ots_por_pedido_id.get(ped_obj.id)
        if ot is None:
            discrepancias.append(f"Falta OrdenTrabajo para pedido {ped_id}.")
        else:
            ot_esp_estado = proyeccion["ots"][ped_id]["estado"]
            if ot.estado.codigo != ot_esp_estado:
                discrepancias.append(f"OT {ped_id} estado {ot.estado.codigo} != {ot_esp_estado}")
            ped_oracle = pedidos_obj_por_id.get(ped_id)
            if ped_oracle and ped_oracle.get("fecha_entrega_programada"):
                f_prog = parsear_fecha(
                    ped_oracle["fecha_entrega_programada"], f"{ped_id}.fecha_prog"
                )
                if ot.fecha_entrega != f_prog:
                    discrepancias.append(
                        f"OT {ped_id} fecha_entrega {ot.fecha_entrega} != {f_prog}"
                    )
            ot_oracle = ots_obj_por_ped.get(ped_id)
            if ot_oracle and (
                not ot.jefe_taller or ot.jefe_taller.username != ot_oracle["jefe_taller"]
            ):
                discrepancias.append(f"OT {ped_id} jefe_taller no coincide con oráculo.")

    recs_esp = proyeccion["recibos"]
    if recibos_qs.count() != len(recs_esp):
        discrepancias.append(
            f"recibos al corte {fecha_corte}: real={recibos_qs.count()} != {len(recs_esp)}"
        )
    for rec_id, r_esp in recs_esp.items():
        rec_obj = recibos_por_id_fuente.get(rec_id)
        if rec_obj is None:
            discrepancias.append(f"Falta recibo {rec_id} al corte {fecha_corte}.")
            continue
        if (
            rec_obj.fecha != parsear_fecha(r_esp["fecha"], f"{rec_id}.fecha")
            or rec_obj.created_by.username != r_esp["actor"]
            or rec_obj.tipo_pago.codigo != r_esp["tipo_pago"]
            or rec_obj.pago_actual != parsear_decimal(r_esp["pago_actual"], f"{rec_id}.pago")
            or rec_obj.a_cuenta != r_esp["a_cuenta_corte"]
            or rec_obj.saldo != r_esp["saldo_corte"]
            or rec_obj.estado != r_esp["estado"]
        ):
            discrepancias.append(f"Recibo {rec_id} difiere del oráculo.")

    notas_esp = proyeccion["notas"]
    if notas_qs.count() != len(notas_esp):
        discrepancias.append(
            f"notas_entrega al corte {fecha_corte}: real={notas_qs.count()} != {len(notas_esp)}"
        )
    for ped_id, fecha_emision_str in notas_esp.items():
        ped_obj = pedidos_por_pf_fuente.get(peds_esp[ped_id]["proforma_id"])
        nota_obj = notas_por_pedido_id.get(ped_obj.id) if ped_obj else None
        if nota_obj is None:
            discrepancias.append(f"Falta NotaEntrega para pedido {ped_id}.")
        elif nota_obj.fecha != parsear_fecha(fecha_emision_str, f"{ped_id}.nota_fecha"):
            discrepancias.append(
                f"NotaEntrega {ped_id} fecha {nota_obj.fecha} != {fecha_emision_str}"
            )

    if movs_por_tipo.get("VENTA", 0) != proyeccion["movimientos_venta"]:
        discrepancias.append(
            f"movimientos VENTA al corte {fecha_corte}: "
            f"{movs_por_tipo.get('VENTA', 0)} != {proyeccion['movimientos_venta']}"
        )
    if movs_por_tipo.get("REVERSA_VENTA", 0) != proyeccion["movimientos_reversa"]:
        discrepancias.append(
            f"movimientos REVERSA_VENTA al corte {fecha_corte}: "
            f"{movs_por_tipo.get('REVERSA_VENTA', 0)} != {proyeccion['movimientos_reversa']}"
        )

    conciliacion_skus: list[dict] = []
    for item in validacion.conciliacion_stock:
        sku = item["sku"]
        prod = productos_por_sku.get(sku)
        stock_actual = prod.stock if prod else None
        esperado_corte = proyeccion["stock_por_sku"][sku]
        coincide_corte = stock_actual == esperado_corte if stock_actual is not None else False
        if not coincide_corte:
            discrepancias.append(
                f"Stock de {sku} al corte {fecha_corte} difiere: {stock_actual} != {esperado_corte}"
            )
        conciliacion_skus.append(
            {
                "sku": sku,
                "apertura_esperada": item["apertura"],
                "saldo_esperado_corte": _formatear_cantidad(esperado_corte),
                "saldo_objetivo_final": item["saldo_objetivo"],
                "saldo_real": str(stock_actual) if stock_actual is not None else None,
                "coincide": coincide_corte,
            }
        )

    # Distribución mensual y por vendedor (cohorte)
    distribucion_cohortes: dict[str, dict] = {}
    for cohorte_key in sorted(
        {p.get("mes_cohorte") or p["fecha"][:7] for p in validacion.proformas}
    ):
        pfs_coh = [
            proformas_por_id_fuente[p["id"]]
            for p in validacion.proformas
            if (p.get("mes_cohorte") or p["fecha"][:7]) == cohorte_key
            and p["id"] in proformas_por_id_fuente
        ]
        peds_coh = [
            pedidos_por_pf_fuente[p["id"]]
            for p in validacion.proformas
            if (p.get("mes_cohorte") or p["fecha"][:7]) == cohorte_key
            and p["id"] in pedidos_por_pf_fuente
        ]
        distribucion_cohortes[cohorte_key] = {
            "proformas_formalizadas": sum(1 for p in pfs_coh if p.estado.codigo != "BORRADOR"),
            "borradores": sum(1 for p in pfs_coh if p.estado.codigo == "BORRADOR"),
            "estados_proforma": dict(Counter(p.estado.codigo for p in pfs_coh)),
            "formalizadas_por_vendedor": dict(
                Counter(p.vendedor.username for p in pfs_coh if p.estado.codigo != "BORRADOR")
            ),
            "estados_pedido": dict(Counter(p.estado.codigo for p in peds_coh)),
            "pedidos_por_vendedor": dict(Counter(p.proforma.vendedor.username for p in peds_coh)),
        }

    entregas_prog_dic = sum(
        1 for ot in ots_qs if ot.fecha_entrega and ot.fecha_entrega.strftime("%Y-%m") == "2026-12"
    )
    entregas_prog_ene = sum(
        1 for ot in ots_qs if ot.fecha_entrega and ot.fecha_entrega.strftime("%Y-%m") == "2027-01"
    )

    if corte_completo:
        resumen = validacion.resumen_validacion
        comparaciones = [
            ("clientes", clientes_qs.count(), resumen["clientes"]),
            ("productos", productos_qs.count(), len(validacion.catalogo)),
            ("proformas", proformas_qs.count(), resumen["proformas"]),
            ("pedidos", pedidos_qs.count(), resumen["pedidos"]),
            (
                "ordenes_trabajo_funcionales",
                len(ots_funcionales),
                resumen["ordenes_trabajo_funcionales"],
            ),
            ("recibos", recibos_qs.count(), resumen["recibos"]),
            ("notas_entrega", notas_qs.count(), resumen["notas"]),
            ("movimientos_venta", movs_por_tipo.get("VENTA", 0), resumen["movimientos_venta"]),
            (
                "movimientos_reversa",
                movs_por_tipo.get("REVERSA_VENTA", 0),
                resumen["movimientos_reversa"],
            ),
            (
                "stock_inicial",
                stock_inicial_total.normalize(),
                Decimal(resumen["stock_apertura"]).normalize(),
            ),
            (
                "stock_final",
                stock_final_total.normalize(),
                Decimal(resumen["stock_cierre"]).normalize(),
            ),
            (
                "importe_pedidos_no_cancelados",
                importe_no_cancelados,
                Decimal(resumen["importe_pedidos_no_cancelados"]),
            ),
            ("pagos_simulados", pagos_totales, Decimal(resumen["pagos_simulados"])),
            (
                "entregas_programadas_diciembre",
                entregas_prog_dic,
                resumen["entregas_programadas_diciembre"],
            ),
            (
                "entregas_programadas_enero",
                entregas_prog_ene,
                resumen["entregas_programadas_enero"],
            ),
        ]
        for nombre, real, esperado in comparaciones:
            if real != esperado:
                discrepancias.append(f"{nombre}: real={real} != esperado={esperado}")

        for coh_key, coh_esp in resumen.get("cohortes", {}).items():
            coh_real = distribucion_cohortes.get(coh_key, {})
            for campo, clave_real in (
                ("proformas_formalizadas", "proformas_formalizadas"),
                ("borradores", "borradores"),
                ("estados_proforma", "estados_proforma"),
                ("formalizadas_por_vendedor", "formalizadas_por_vendedor"),
                ("estados_pedido_al_corte_virtual", "estados_pedido"),
                ("pedidos_por_vendedor", "pedidos_por_vendedor"),
            ):
                if coh_real.get(clave_real) != coh_esp.get(campo):
                    discrepancias.append(
                        f"Cohorte {coh_key}.{campo}: "
                        f"{coh_real.get(clave_real)} != {coh_esp.get(campo)}"
                    )

        # Verificar movimientos_esperados.json individualmente
        movs_por_pedido_sku = Counter(
            (
                m.pedido_id
                or (m.movimiento_referencia.pedido_id if m.movimiento_referencia else None),
                m.producto.sku,
                m.tipo_movimiento.codigo,
                m.cantidad,
            )
            for m in movs_qs
            if m.pedido_id is not None or m.movimiento_referencia is not None
        )
        for m_esp in validacion.movimientos_esperados:
            ped_obj = pedidos_por_pf_fuente.get(peds_esp[m_esp["pedido_id"]]["proforma_id"])
            llave = (
                ped_obj.id if ped_obj else None,
                m_esp["sku"],
                m_esp["tipo"],
                parsear_decimal(m_esp["cantidad"], "mov.cantidad"),
            )
            if movs_por_pedido_sku.get(llave, 0) != 1:
                discrepancias.append(f"Movimiento esperado faltante o duplicado: {m_esp}")

    return {
        "corte_completo": corte_completo,
        "fecha_corte": fecha_corte.isoformat(),
        "metricas": {
            "clientes": clientes_qs.count(),
            "productos": productos_qs.count(),
            "proformas_total": proformas_qs.count(),
            "proformas_formalizadas": formalizadas,
            "proformas_borradores": borradores,
            "estados_proforma": dict(estados_proforma),
            "pedidos": pedidos_qs.count(),
            "estados_pedido": dict(estados_pedido),
            "ordenes_trabajo_funcionales": len(ots_funcionales),
            "estados_ot_funcionales": dict(estados_ot_funcionales),
            "ordenes_trabajo_tecnicas_catalogo": len(ots_tecnicas),
            "ordenes_trabajo_totales": ots_qs.count(),
            "entregas_programadas_diciembre": entregas_prog_dic,
            "entregas_programadas_enero": entregas_prog_ene,
            "recibos": recibos_qs.count(),
            "notas_entrega": notas_qs.count(),
            "movimientos_por_tipo": dict(movs_por_tipo),
            "stock_inicial": _formatear_cantidad(stock_inicial_total),
            "stock_final": _formatear_cantidad(stock_final_total),
            "importe_pedidos_no_cancelados": f"{importe_no_cancelados:.2f}",
            "pagos_simulados": f"{pagos_totales:.2f}",
            "saldo_pendiente": f"{saldo_pendiente:.2f}",
            "existencias_negativas": len(stock_negativo),
            "bajo_pedido_con_stock": len(bajo_pedido_con_stock),
            "movimientos_venta_duplicados": len(movimientos_venta_duplicados),
        },
        "distribucion_cohortes": distribucion_cohortes,
        "conciliacion_skus": conciliacion_skus,
        "duplicados_mov_pedido_count": duplicados_mov_pedido.count(),
        "discrepancias": discrepancias,
        "conforme": len(discrepancias) == 0,
    }
