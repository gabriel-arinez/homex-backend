"""Auditoría y conciliación de datos importados contra los oráculos del paquete."""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import date
from decimal import Decimal

from django.db.models import Sum

from apps.catalogo.models import Producto
from apps.clientes.models import Cliente
from apps.movimientos_stock.models import MovimientoStock
from apps.notas_entrega.models import NotaEntrega
from apps.ordenes_trabajo.models import OrdenTrabajo
from apps.pedidos.models import Pedido
from apps.proformas.importador_homex.validacion import ResultadoValidacionEscenario
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


def auditar_escenario(
    validacion: ResultadoValidacionEscenario,
    *,
    fecha_corte: date,
) -> dict:
    """Contrasta la base de datos contra los oráculos del escenario sin modificar registros."""
    corte_completo = fecha_corte >= date.fromisoformat(
        validacion.resumen_validacion["corte_virtual"]
    )

    skus_escenario = [p["sku"] for p in validacion.catalogo]
    productos_qs = Producto.objects.filter(sku__in=skus_escenario)
    productos_por_sku = {p.sku: p for p in productos_qs}

    clientes_qs = Cliente.objects.filter(observaciones__contains=MARCADOR_ESCENARIO)

    claves_pf = {
        clave_idempotencia_escenario("PROFORMA", pf["id"]): pf["id"] for pf in validacion.proformas
    }
    proformas_qs = Proforma.objects.filter(clave_idempotencia__in=claves_pf.keys()).select_related(
        "estado"
    )
    proformas_por_id_fuente = {claves_pf[p.clave_idempotencia]: p for p in proformas_qs}

    pedidos_qs = Pedido.objects.filter(proforma__in=proformas_qs).select_related(
        "estado", "proforma"
    )
    ots_qs = OrdenTrabajo.objects.filter(pedido__in=pedidos_qs).select_related(
        "estado", "jefe_taller", "pedido__proforma"
    )
    recibos_qs = Recibo.objects.filter(pedido__in=pedidos_qs, estado="EMITIDO")
    notas_qs = NotaEntrega.objects.filter(pedido__in=pedidos_qs)
    movs_qs = MovimientoStock.objects.filter(producto__in=productos_qs).select_related(
        "tipo_movimiento", "producto"
    )

    # Separar órdenes funcionales (con muebles a medida) de órdenes técnicas (solo catálogo)
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
    # Verificar que no haya más de un movimiento VENTA por (pedido, producto)
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

    # Verificar separación documental vs simulado
    doc_mezclado = Producto.objects.filter(
        sku__in=skus_escenario, observaciones__contains=MARCADOR_DOCUMENTAL
    ).exists()
    if doc_mezclado:
        discrepancias.append("Se detectó mezcla de marcadores documentales en productos simulados.")

    conciliacion_skus: list[dict] = []
    for item in validacion.conciliacion_stock:
        sku = item["sku"]
        prod = productos_por_sku.get(sku)
        stock_actual = prod.stock if prod else None
        objetivo = Decimal(str(item["saldo_objetivo"]))
        coincide = stock_actual == objetivo if stock_actual is not None else False
        if corte_completo and not coincide:
            discrepancias.append(
                f"Stock final de {sku} difiere del objetivo: {stock_actual} != {objetivo}"
            )
        conciliacion_skus.append(
            {
                "sku": sku,
                "apertura_esperada": item["apertura"],
                "saldo_objetivo": item["saldo_objetivo"],
                "saldo_real": str(stock_actual) if stock_actual is not None else None,
                "coincide": coincide,
            }
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
        ]
        for nombre, real, esperado in comparaciones:
            if real != esperado:
                discrepancias.append(f"{nombre}: real={real} != esperado={esperado}")

        # Verificar pedidos individuales contra pedidos_objetivo.json
        for po in validacion.pedidos_objetivo:
            pf_obj = proformas_por_id_fuente.get(po["proforma_id"])
            if pf_obj is None:
                discrepancias.append(f"Falta proforma {po['proforma_id']} para pedido {po['id']}.")
                continue
            ped = getattr(pf_obj, "pedido", None)
            if ped is None:
                discrepancias.append(f"Falta pedido para proforma {po['proforma_id']}.")
                continue
            if ped.estado.codigo != po["estado_objetivo"]:
                discrepancias.append(
                    f"Pedido {po['id']} estado {ped.estado.codigo} != {po['estado_objetivo']}"
                )
            if pf_obj.total != Decimal(po["total"]):
                discrepancias.append(f"Pedido {po['id']} total {pf_obj.total} != {po['total']}")

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
        "conciliacion_skus": conciliacion_skus,
        "duplicados_mov_pedido_count": duplicados_mov_pedido.count(),
        "discrepancias": discrepancias,
        "conforme": len(discrepancias) == 0,
    }
