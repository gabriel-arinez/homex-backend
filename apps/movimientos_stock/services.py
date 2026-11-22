import csv
import io
import uuid
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Case, DecimalField, F, Q, Sum, Value, When, Window
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.catalogo.models import Producto, ValorCatalogo
from apps.catalogo.services import validar_cantidad_segun_unidad
from apps.core.exceptions import ConflictoComercial
from apps.core.permissions import es_administrador_comercial
from apps.movimientos_stock.models import MovimientoStock

MOTIVO_CORRECCION_EXCEPCIONAL = "CORRECCION_EXCEPCIONAL"

MOTIVOS_ENTRADA: dict[str, str] = {
    "REPOSICION": "Reposición",
    "REGULARIZACION_POSITIVA": "Regularización positiva",
    MOTIVO_CORRECCION_EXCEPCIONAL: "Corrección excepcional",
}

MOTIVOS_SALIDA: dict[str, str] = {
    "MERMA": "Merma",
    "DANO": "Daño",
    "USO_INTERNO": "Uso interno",
    "REGULARIZACION_NEGATIVA": "Regularización negativa",
    MOTIVO_CORRECCION_EXCEPCIONAL: "Corrección excepcional",
}

TODOS_LOS_MOTIVOS: dict[str, str] = {**MOTIVOS_ENTRADA, **MOTIVOS_SALIDA}


def catalogo_motivos_ajuste() -> dict[str, list[dict[str, object]]]:
    return {
        "ENTRADA": [
            {
                "codigo": codigo,
                "nombre": nombre,
                "requiere_observaciones": codigo == MOTIVO_CORRECCION_EXCEPCIONAL,
            }
            for codigo, nombre in MOTIVOS_ENTRADA.items()
        ],
        "SALIDA": [
            {
                "codigo": codigo,
                "nombre": nombre,
                "requiere_observaciones": codigo == MOTIVO_CORRECCION_EXCEPCIONAL,
            }
            for codigo, nombre in MOTIVOS_SALIDA.items()
        ],
    }


def label_motivo(codigo: str | None) -> str | None:
    if not codigo:
        return None
    return TODOS_LOS_MOTIVOS.get(codigo, codigo)


def _sanitizar_celda_csv(valor: object) -> str:
    texto = "" if valor is None else str(valor)
    if not texto:
        return ""
    limpio = texto.lstrip(" \t\r\n")
    if texto[0] in ("\t", "\r", "\n") or (limpio and limpio[0] in ("=", "+", "-", "@")):
        return f"'{texto}"
    return texto


def _normalizar_clave_idempotencia(clave: str | uuid.UUID | None) -> uuid.UUID:
    if clave is None or str(clave).strip() == "":
        raise ValidationError(
            {
                "clave_idempotencia": (
                    "Se requiere una clave UUID válida en Idempotency-Key o clave_idempotencia."
                )
            }
        )
    if isinstance(clave, uuid.UUID):
        return clave
    try:
        return uuid.UUID(str(clave).strip())
    except ValueError as exc:
        raise ValidationError({"clave_idempotencia": "Debe ser un UUID válido."}) from exc


def _verificar_payload_idempotente(
    existente: MovimientoStock,
    *,
    actor_id: int,
    producto_id: int,
    tipo_operacion: str,
    cantidad: Decimal,
    motivo: str,
    obs_limpia: str,
) -> None:
    cantidad_esperada = cantidad if tipo_operacion == "ENTRADA" else -cantidad
    obs_esperada = obs_limpia or TODOS_LOS_MOTIVOS.get(motivo, "")
    coincide = (
        existente.created_by_id == actor_id
        and existente.producto_id == producto_id
        and existente.cantidad == cantidad_esperada
        and existente.motivo == motivo
        and (existente.observaciones or "") == obs_esperada
    )
    if not coincide:
        raise ConflictoComercial(
            "La clave de idempotencia ya fue utilizada con una operación diferente."
        )


@transaction.atomic
def registrar_ajuste_stock(
    *,
    producto_id: int,
    tipo_operacion: str,
    cantidad: Decimal,
    motivo: str,
    observaciones: str | None,
    actor,
    clave_idempotencia: str | uuid.UUID | None = None,
) -> tuple[MovimientoStock, bool]:
    """Registra un ajuste manual (ENTRADA o SALIDA) de forma transaccional e idempotente."""
    if not es_administrador_comercial(actor):
        raise PermissionDenied("Solo la administración comercial puede registrar ajustes de stock.")

    clave_uuid = _normalizar_clave_idempotencia(clave_idempotencia)
    obs_limpia = (observaciones or "").strip()

    if cantidad <= 0:
        raise ValidationError({"cantidad": "La cantidad debe ser mayor a cero."})

    if tipo_operacion not in {"ENTRADA", "SALIDA"}:
        raise ValidationError({"tipo_operacion": "Debe ser ENTRADA o SALIDA."})

    motivos_validos = MOTIVOS_ENTRADA if tipo_operacion == "ENTRADA" else MOTIVOS_SALIDA
    if motivo not in motivos_validos:
        raise ValidationError({"motivo": f"Motivo inválido para {tipo_operacion}."})

    if motivo == MOTIVO_CORRECCION_EXCEPCIONAL and not obs_limpia:
        raise ValidationError(
            {
                "observaciones": (
                    "Las correcciones excepcionales requieren una observación justificativa."
                )
            }
        )

    existente = (
        MovimientoStock.objects.select_related(
            "producto",
            "producto__unidad_stock",
            "tipo_movimiento",
            "pedido",
            "movimiento_referencia__pedido",
            "created_by",
        )
        .filter(clave_idempotencia=clave_uuid)
        .first()
    )
    if existente is not None:
        _verificar_payload_idempotente(
            existente,
            actor_id=actor.id,
            producto_id=producto_id,
            tipo_operacion=tipo_operacion,
            cantidad=cantidad,
            motivo=motivo,
            obs_limpia=obs_limpia,
        )
        return existente, True

    try:
        producto = (
            Producto.objects.select_related("unidad_stock").select_for_update().get(pk=producto_id)
        )
    except Producto.DoesNotExist as exc:
        raise ValidationError({"producto": "El producto indicado no existe."}) from exc

    try:
        validar_cantidad_segun_unidad(cantidad, producto.unidad_stock.codigo, permitir_cero=False)
    except ValidationError as exc:
        raise ValidationError({"cantidad": exc.detail}) from exc

    cantidad_con_signo = cantidad if tipo_operacion == "ENTRADA" else -cantidad
    if tipo_operacion == "SALIDA" and (producto.stock + cantidad_con_signo) < 0:
        raise ValidationError(
            {
                "cantidad": (
                    f"Stock insuficiente para la salida. Stock actual: "
                    f"{producto.stock} {producto.unidad_stock.codigo}."
                )
            }
        )

    tipo_ajuste = ValorCatalogo.objects.get(
        concepto__codigo="TIPO_MOVIMIENTO",
        codigo="AJUSTE",
    )
    obs_final = obs_limpia or motivos_validos[motivo]

    try:
        with transaction.atomic():
            movimiento = MovimientoStock.objects.create(
                producto=producto,
                fecha=timezone.now(),
                tipo_movimiento=tipo_ajuste,
                cantidad=cantidad_con_signo,
                motivo=motivo,
                observaciones=obs_final,
                created_by=actor,
                clave_idempotencia=clave_uuid,
            )
    except IntegrityError:
        existente = MovimientoStock.objects.select_related(
            "producto",
            "producto__unidad_stock",
            "tipo_movimiento",
            "pedido",
            "movimiento_referencia__pedido",
            "created_by",
        ).get(clave_idempotencia=clave_uuid)
        _verificar_payload_idempotente(
            existente,
            actor_id=actor.id,
            producto_id=producto_id,
            tipo_operacion=tipo_operacion,
            cantidad=cantidad,
            motivo=motivo,
            obs_limpia=obs_limpia,
        )
        return existente, True

    movimiento = MovimientoStock.objects.select_related(
        "producto",
        "producto__unidad_stock",
        "tipo_movimiento",
        "pedido",
        "movimiento_referencia__pedido",
        "created_by",
    ).get(pk=movimiento.pk)
    return movimiento, False


def calcular_saldos_y_resumen(
    queryset_filtrado,
    *,
    producto_id: int | None,
    fecha_desde=None,
    fecha_hasta=None,
) -> dict:
    """Calcula resumen del período y saldos históricos cuando existe un único producto confiable."""
    if producto_id is None:
        return {
            "saldo_reconstruible": False,
            "limitacion_saldo": (
                "Selecciona un producto específico para calcular saldos históricos "
                "y totales sin mezclar unidades."
            ),
            "resumen": None,
            "saldos_por_id": {},
        }

    producto = Producto.objects.select_related("unidad_stock").filter(pk=producto_id).first()
    if producto is None:
        return {
            "saldo_reconstruible": False,
            "limitacion_saldo": "El producto seleccionado no existe.",
            "resumen": None,
            "saldos_por_id": {},
        }

    agregados = queryset_filtrado.aggregate(
        total_entradas=Coalesce(
            Sum(
                Case(
                    When(cantidad__gt=0, then=F("cantidad")),
                    default=Value(Decimal("0")),
                    output_field=DecimalField(max_digits=14, decimal_places=4),
                )
            ),
            Value(Decimal("0")),
            output_field=DecimalField(max_digits=14, decimal_places=4),
        ),
        total_salidas=Coalesce(
            Sum(
                Case(
                    When(cantidad__lt=0, then=-F("cantidad")),
                    default=Value(Decimal("0")),
                    output_field=DecimalField(max_digits=14, decimal_places=4),
                )
            ),
            Value(Decimal("0")),
            output_field=DecimalField(max_digits=14, decimal_places=4),
        ),
        variacion_neta=Coalesce(
            Sum("cantidad"),
            Value(Decimal("0")),
            output_field=DecimalField(max_digits=14, decimal_places=4),
        ),
    )

    total_historico = MovimientoStock.objects.filter(producto_id=producto_id).aggregate(
        total=Coalesce(Sum("cantidad"), Value(Decimal("0")))
    )["total"]

    saldo_reconstruible = total_historico == producto.stock
    limitacion_saldo = None
    saldos_por_id: dict[int, dict[str, str]] = {}
    saldo_inicial_periodo: str | None = None
    saldo_final_periodo: str | None = None

    if saldo_reconstruible:
        movs_con_saldo = list(
            MovimientoStock.objects.filter(producto_id=producto_id)
            .annotate(
                saldo_posterior=Window(
                    expression=Sum("cantidad"),
                    order_by=[F("fecha").asc(), F("id").asc()],
                )
            )
            .values("id", "cantidad", "saldo_posterior")
        )
        for row in movs_con_saldo:
            saldo_post = row["saldo_posterior"]
            saldo_ant = saldo_post - row["cantidad"]
            saldos_por_id[row["id"]] = {
                "saldo_anterior": str(saldo_ant),
                "saldo_posterior": str(saldo_post),
            }

        if fecha_desde is not None:
            saldo_ini = MovimientoStock.objects.filter(
                producto_id=producto_id, fecha__date__lt=fecha_desde
            ).aggregate(total=Coalesce(Sum("cantidad"), Value(Decimal("0"))))["total"]
        else:
            saldo_ini = Decimal("0")

        if fecha_hasta is not None:
            saldo_fin = MovimientoStock.objects.filter(
                producto_id=producto_id, fecha__date__lte=fecha_hasta
            ).aggregate(total=Coalesce(Sum("cantidad"), Value(Decimal("0"))))["total"]
        else:
            saldo_fin = producto.stock

        saldo_inicial_periodo = str(saldo_ini)
        saldo_final_periodo = str(saldo_fin)
    else:
        limitacion_saldo = (
            "Los movimientos históricos de este producto no coinciden exactamente con su stock "
            f"actual ({total_historico} vs {producto.stock}); no se inventarán saldos históricos."
        )

    return {
        "saldo_reconstruible": saldo_reconstruible,
        "limitacion_saldo": limitacion_saldo,
        "resumen": {
            "producto_id": producto.id,
            "unidad_codigo": producto.unidad_stock.codigo,
            "unidad_nombre": producto.unidad_stock.nombre,
            "stock_actual": str(producto.stock),
            "total_entradas": str(agregados["total_entradas"]),
            "total_salidas": str(agregados["total_salidas"]),
            "variacion_neta": str(agregados["variacion_neta"]),
            "saldo_inicial_periodo": saldo_inicial_periodo,
            "saldo_final_periodo": saldo_final_periodo,
            "cantidad_movimientos": queryset_filtrado.filter(Q(pk__isnull=False)).count(),
        },
        "saldos_por_id": saldos_por_id,
    }


def _iterar_filas_movimientos(movimientos, *, saldos_por_id: dict[int, dict[str, str]]):
    for mov in movimientos:
        responsable = (
            mov.created_by.get_full_name().strip() or mov.created_by.get_username()
            if mov.created_by
            else "Sistema"
        )
        pedido_rel = mov.pedido_id
        if pedido_rel is None and mov.tipo_movimiento.codigo == "REVERSA_VENTA":
            ref = mov.movimiento_referencia
            pedido_rel = ref.pedido_id if ref is not None else None
        saldos = saldos_por_id.get(mov.id)
        direccion = "Entrada" if mov.cantidad > 0 else "Salida"
        yield {
            "id": mov.id,
            "fecha": timezone.localtime(mov.fecha).strftime("%Y-%m-%d %H:%M:%S"),
            "sku": _sanitizar_celda_csv(mov.producto.sku or ""),
            "producto": _sanitizar_celda_csv(mov.producto.nombre),
            "unidad": _sanitizar_celda_csv(mov.producto.unidad_stock.nombre),
            "tipo": _sanitizar_celda_csv(mov.tipo_movimiento.nombre),
            "direccion": direccion,
            "cantidad": str(mov.cantidad),
            "cantidad_num": float(mov.cantidad),
            "motivo": _sanitizar_celda_csv(label_motivo(mov.motivo) or ""),
            "observaciones": _sanitizar_celda_csv(mov.observaciones or ""),
            "pedido": pedido_rel or "",
            "referencia": mov.movimiento_referencia_id or "",
            "responsable": _sanitizar_celda_csv(responsable),
            "saldo_anterior": saldos["saldo_anterior"] if saldos else "",
            "saldo_posterior": saldos["saldo_posterior"] if saldos else "",
        }


_COLUMNAS_EXPORTACION = [
    "ID",
    "Fecha",
    "SKU",
    "Producto",
    "Unidad",
    "Tipo",
    "Dirección",
    "Cantidad",
    "Motivo",
    "Observaciones",
    "Pedido",
    "Movimiento Referencia",
    "Responsable",
    "Saldo Anterior",
    "Saldo Posterior",
]


def generar_csv_movimientos(movimientos, *, saldos_por_id: dict[int, dict[str, str]]) -> str:
    """Genera CSV UTF-8 con BOM compatible con Excel para los movimientos filtrados."""
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(_COLUMNAS_EXPORTACION)

    for row in _iterar_filas_movimientos(movimientos, saldos_por_id=saldos_por_id):
        writer.writerow(
            [
                row["id"],
                row["fecha"],
                row["sku"],
                row["producto"],
                row["unidad"],
                row["tipo"],
                row["direccion"],
                row["cantidad"],
                row["motivo"],
                row["observaciones"],
                row["pedido"],
                row["referencia"],
                row["responsable"],
                row["saldo_anterior"],
                row["saldo_posterior"],
            ]
        )
    return buffer.getvalue()


def generar_excel_movimientos(
    movimientos,
    *,
    saldos_por_id: dict[int, dict[str, str]],
    resumen: dict | None,
    fecha_desde,
    fecha_hasta,
    producto: Producto | None = None,
) -> bytes:
    """Genera un archivo Excel (.xlsx) corporativo HOMEX con ajuste de texto en todas las celdas."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Movimientos de stock"
    ws.views.sheetView[0].showGridLines = True

    thin_side = Side(style="thin", color="D9DEE5")
    cell_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    title_font = Font(name="Calibri", size=14, bold=True, color="B91C1C")
    meta_font = Font(name="Calibri", size=10, color="334155")
    summary_font = Font(name="Calibri", size=10, bold=True, color="0F172A")
    header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    body_font = Font(name="Calibri", size=10, color="0F172A")

    header_fill = PatternFill(start_color="B91C1C", end_color="B91C1C", fill_type="solid")
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    summary_fill = PatternFill(start_color="FEF2F2", end_color="FEF2F2", fill_type="solid")

    wrap_left = Alignment(horizontal="left", vertical="top", wrap_text=True)
    wrap_right = Alignment(horizontal="right", vertical="top", wrap_text=True)
    wrap_center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Fila 1: Título
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(_COLUMNAS_EXPORTACION))
    ws.cell(row=1, column=1, value="HOMEX — Reporte de Movimientos de Stock")
    ws.cell(row=1, column=1).font = title_font
    ws.cell(row=1, column=1).alignment = wrap_left
    ws.row_dimensions[1].height = 24

    # Fila 2: Período y producto
    periodo_txt = f"Período: {fecha_desde.isoformat()} al {fecha_hasta.isoformat()}"
    if producto is not None:
        sku_part = f"[{producto.sku}] " if producto.sku else ""
        periodo_txt += (
            f"   |   Producto: {_sanitizar_celda_csv(sku_part + producto.nombre)}"
            f" ({_sanitizar_celda_csv(producto.unidad_stock.nombre)})"
        )
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(_COLUMNAS_EXPORTACION))
    ws.cell(row=2, column=1, value=periodo_txt)
    ws.cell(row=2, column=1).font = meta_font
    ws.cell(row=2, column=1).alignment = wrap_left
    ws.row_dimensions[2].height = 20

    current_row = 3
    if resumen is not None:
        resumen_txt = (
            f"Saldo inicial: {resumen.get('saldo_inicial_periodo') or 'N/D'}   |   "
            f"Entradas: +{resumen.get('total_entradas', '0')}   |   "
            f"Salidas: -{resumen.get('total_salidas', '0')}   |   "
            f"Saldo final: {resumen.get('saldo_final_periodo') or 'N/D'}   |   "
            f"Movimientos: {resumen.get('cantidad_movimientos', 0)}"
        )
        ws.merge_cells(
            start_row=current_row,
            start_column=1,
            end_row=current_row,
            end_column=len(_COLUMNAS_EXPORTACION),
        )
        c_sum = ws.cell(row=current_row, column=1, value=resumen_txt)
        c_sum.font = summary_font
        c_sum.fill = summary_fill
        c_sum.alignment = wrap_left
        ws.row_dimensions[current_row].height = 22
        current_row += 1

    header_row = current_row + 1
    ws.row_dimensions[header_row].height = 26
    for col_idx, titulo in enumerate(_COLUMNAS_EXPORTACION, start=1):
        cell = ws.cell(row=header_row, column=col_idx, value=titulo)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = wrap_center
        cell.border = cell_border

    numeric_cols = {1, 8, 11, 12, 14, 15}
    row_idx = header_row + 1
    for idx, row in enumerate(_iterar_filas_movimientos(movimientos, saldos_por_id=saldos_por_id)):
        valores = [
            row["id"],
            row["fecha"],
            row["sku"],
            row["producto"],
            row["unidad"],
            row["tipo"],
            row["direccion"],
            row["cantidad_num"],
            row["motivo"],
            row["observaciones"],
            row["pedido"],
            row["referencia"],
            row["responsable"],
            float(row["saldo_anterior"]) if row["saldo_anterior"] != "" else "",
            float(row["saldo_posterior"]) if row["saldo_posterior"] != "" else "",
        ]
        use_zebra = idx % 2 == 1
        for col_idx, val in enumerate(valores, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = body_font
            cell.border = cell_border
            cell.alignment = wrap_right if col_idx in numeric_cols else wrap_left
            if use_zebra:
                cell.fill = zebra_fill
        row_idx += 1

    anchos = [8, 19, 16, 30, 12, 20, 12, 13, 22, 34, 11, 16, 22, 15, 15]
    for col_idx, ancho in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = ancho

    ws.freeze_panes = f"A{header_row + 1}"

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
