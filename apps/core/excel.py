"""Utilidades compartidas de exportación Excel (.xlsx) corporativa HOMEX."""

from __future__ import annotations

import datetime as dt
import io
from decimal import Decimal
from typing import Iterable, Sequence

from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


def sanitizar_celda_excel(valor) -> str:
    """Neutraliza prefijos de fórmulas para prevenir inyección en hojas de cálculo."""
    texto = "" if valor is None else str(valor)
    if texto and texto[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{texto}"
    return texto


def _normalizar_valor_celda(valor):
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, (int, float)):
        return valor
    if isinstance(valor, dt.datetime):
        if timezone.is_aware(valor):
            return timezone.localtime(valor).replace(tzinfo=None)
        return valor
    if isinstance(valor, dt.date):
        return valor
    return sanitizar_celda_excel(valor)


def generar_excel_corporativo(
    *,
    titulo_hoja: str,
    titulo_reporte: str,
    columnas: Sequence[str],
    filas: Iterable[Sequence[object]],
    subtitulo_filtros: str | None = None,
    resumen: str | None = None,
    anchos: Sequence[int] | None = None,
    numeric_cols: set[int] | None = None,
    integer_cols: set[int] | None = None,
    currency_cols: set[int] | None = None,
    date_cols: set[int] | None = None,
    datetime_cols: set[int] | None = None,
) -> bytes:
    """Genera un archivo .xlsx con el diseño institucional HOMEX."""
    wb = Workbook()
    ws = wb.active
    ws.title = titulo_hoja[:31]
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

    total_cols = max(1, len(columnas))
    numeric_set = set(numeric_cols or ())
    integer_set = set(integer_cols or ())
    currency_set = set(currency_cols or ())
    date_set = set(date_cols or ())
    datetime_set = set(datetime_cols or ())
    right_aligned = numeric_set | integer_set | currency_set

    # Fila 1: Título
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
    ws.cell(row=1, column=1, value=titulo_reporte)
    ws.cell(row=1, column=1).font = title_font
    ws.cell(row=1, column=1).alignment = wrap_left
    ws.row_dimensions[1].height = 24

    current_row = 2
    # Fila 2: Filtros aplicados
    filtro_texto = subtitulo_filtros or "Filtros: Ninguno (listado completo)"
    ws.merge_cells(
        start_row=current_row, start_column=1, end_row=current_row, end_column=total_cols
    )
    ws.cell(row=current_row, column=1, value=sanitizar_celda_excel(filtro_texto))
    ws.cell(row=current_row, column=1).font = meta_font
    ws.cell(row=current_row, column=1).alignment = wrap_left
    ws.row_dimensions[current_row].height = 20
    current_row += 1

    # Fila opcional de resumen
    if resumen:
        ws.merge_cells(
            start_row=current_row,
            start_column=1,
            end_row=current_row,
            end_column=total_cols,
        )
        c_sum = ws.cell(row=current_row, column=1, value=sanitizar_celda_excel(resumen))
        c_sum.font = summary_font
        c_sum.fill = summary_fill
        c_sum.alignment = wrap_left
        ws.row_dimensions[current_row].height = 22
        current_row += 1

    header_row = current_row + 1
    ws.row_dimensions[header_row].height = 26
    for col_idx, titulo in enumerate(columnas, start=1):
        cell = ws.cell(row=header_row, column=col_idx, value=titulo)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = wrap_center
        cell.border = cell_border

    row_idx = header_row + 1
    row_count = 0
    for idx, row in enumerate(filas):
        row_count += 1
        use_zebra = idx % 2 == 1
        for col_idx, raw_val in enumerate(row, start=1):
            val = _normalizar_valor_celda(raw_val)
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = body_font
            cell.border = cell_border
            cell.alignment = wrap_right if col_idx in right_aligned else wrap_left
            if use_zebra:
                cell.fill = zebra_fill
            if isinstance(val, (int, float)):
                if col_idx in currency_set:
                    cell.number_format = "#,##0.00"
                elif col_idx in integer_set:
                    cell.number_format = "#,##0"
                elif col_idx in numeric_set:
                    cell.number_format = "#,##0.####"
            elif isinstance(val, dt.datetime) and (
                col_idx in datetime_set or col_idx not in date_set
            ):
                cell.number_format = "dd/mm/yyyy hh:mm"
            elif isinstance(val, dt.date):
                cell.number_format = "dd/mm/yyyy"
        row_idx += 1

    if row_count == 0:
        ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=total_cols)
        empty_cell = ws.cell(
            row=row_idx, column=1, value="Sin registros para los filtros seleccionados."
        )
        empty_cell.font = meta_font
        empty_cell.alignment = wrap_center
        ws.row_dimensions[row_idx].height = 22

    if anchos:
        for col_idx, ancho in enumerate(anchos, start=1):
            ws.column_dimensions[get_column_letter(col_idx)].width = ancho
    else:
        for col_idx in range(1, total_cols + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 18

    ws.freeze_panes = f"A{header_row + 1}"

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def respuesta_excel(*, contenido: bytes, filename: str) -> HttpResponse:
    response = HttpResponse(
        contenido,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
