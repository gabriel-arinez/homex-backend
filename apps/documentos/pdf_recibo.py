from io import BytesIO
from pathlib import Path

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

from apps.recibos.models import Recibo

HOMEX_DATOS_COMERCIALES = {
    "nombre": "HOMEX",
    "subtitulo": "Comprobante oficial de cobro",
}


def _draw_wrapped_paragraph(
    c: Canvas,
    text: str,
    x: float,
    y_top: float,
    max_width: float,
    max_height: float,
    *,
    font_name: str = "Homex",
    sizes: tuple[float, ...] = (8.5, 7.5, 6.8),
    color: str = "#0f172a",
    leading_factor: float = 1.25,
) -> float:
    """Dibuja texto con ajuste de línea y reducción controlada de tamaño dentro de max_height."""
    from xml.sax.saxutils import escape

    safe_text = escape(text or "—").replace("\n", "<br/>")
    chosen_p = None
    chosen_h = 0.0
    for size in sizes:
        style = ParagraphStyle(
            name=f"recibo_{font_name}_{size}",
            fontName=font_name,
            fontSize=size,
            leading=size * leading_factor,
            textColor=colors.HexColor(color),
        )
        para = Paragraph(safe_text, style)
        _, h = para.wrap(max_width, max_height)
        chosen_p = para
        chosen_h = h
        if h <= max_height:
            break

    if chosen_p is not None:
        if chosen_h > max_height:
            # Recorta progresivamente si un texto extremo supera el alto máximo de la mitad.
            for cut in (220, 160, 110, 80):
                trimmed = escape((text or "")[:cut].rstrip() + "…")
                style = ParagraphStyle(
                    name=f"recibo_trim_{cut}",
                    fontName=font_name,
                    fontSize=sizes[-1],
                    leading=sizes[-1] * leading_factor,
                    textColor=colors.HexColor(color),
                )
                para = Paragraph(trimmed, style)
                _, h = para.wrap(max_width, max_height)
                chosen_p = para
                chosen_h = h
                if h <= max_height:
                    break
        chosen_p.drawOn(c, x, y_top - chosen_h)
    return chosen_h


def _draw_recibo_copy(
    c: Canvas,
    *,
    recibo: Recibo,
    moneda_codigo: str,
    fecha_texto: str,
    pago_texto: str,
    total_texto: str,
    a_cuenta_texto: str,
    saldo_texto: str,
    x: float,
    y_top: float,
    width: float,
    height: float,
    logo_path: Path,
) -> None:
    red = colors.HexColor("#b91c1c")
    dark = colors.HexColor("#0f172a")
    grey = colors.HexColor("#334155")
    muted = colors.HexColor("#64748b")
    border = colors.HexColor("#d9dee5")
    pale = colors.HexColor("#f8fafc")

    # Contenedor exterior limpio de cada mitad
    c.saveState()
    c.setStrokeColor(border)
    c.setLineWidth(0.75)
    c.setFillColor(colors.white)
    c.roundRect(x, y_top - height, width, height, 6, stroke=1, fill=1)

    pad = 11
    inner_x = x + pad
    inner_w = width - 2 * pad
    cursor_y = y_top - pad

    # Encabezado: Logo + datos comerciales centralizados (izq) | Copia + N° + Fecha (der)
    logo_h = 10.5 * mm
    logo_w = logo_h * (2400 / 750)
    if logo_path.exists():
        c.drawImage(
            str(logo_path),
            inner_x,
            cursor_y - logo_h,
            width=logo_w,
            height=logo_h,
            mask="auto",
            preserveAspectRatio=True,
        )
    else:
        c.setFont("Homex-Bold", 14)
        c.setFillColor(red)
        c.drawString(inner_x, cursor_y - 14, HOMEX_DATOS_COMERCIALES["nombre"])

    c.setFont("Homex", 7.5)
    c.setFillColor(muted)
    c.drawString(inner_x, cursor_y - logo_h - 9, HOMEX_DATOS_COMERCIALES["subtitulo"])

    # Número, fecha y estado en la esquina superior derecha
    c.setFillColor(dark)
    c.setFont("Homex-Bold", 12)
    c.drawRightString(inner_x + inner_w, cursor_y - 11, f"RECIBO N° {recibo.numero}")
    c.setFillColor(grey)
    c.setFont("Homex", 8)
    c.drawRightString(inner_x + inner_w, cursor_y - 23, fecha_texto)

    if recibo.estado == "ANULADO":
        c.setFillColor(red)
        c.setFont("Homex-Bold", 8.5)
        c.drawRightString(inner_x + inner_w, cursor_y - 35, "ANULADO")

    cursor_y -= logo_h + 15
    c.setStrokeColor(red)
    c.setLineWidth(1.0)
    c.line(inner_x, cursor_y, inner_x + inner_w, cursor_y)
    cursor_y -= 9

    # Fila 1: Recibido de (izq 64%) + Monto recibido (der 34%)
    gap = 8
    left_w = inner_w * 0.64
    right_w = inner_w - left_w - gap

    payer_box_h = 38
    c.setFillColor(pale)
    c.setStrokeColor(border)
    c.setLineWidth(0.5)
    c.roundRect(inner_x, cursor_y - payer_box_h, left_w, payer_box_h, 4, stroke=1, fill=1)
    c.setFillColor(muted)
    c.setFont("Homex-Bold", 6.8)
    c.drawString(inner_x + 7, cursor_y - 10, "RECIBIDO DE")
    _draw_wrapped_paragraph(
        c,
        recibo.nombre_completo,
        inner_x + 7,
        cursor_y - 13,
        left_w - 14,
        payer_box_h - 16,
        font_name="Homex-Bold",
        sizes=(9.0, 8.0, 7.0),
    )

    amt_x = inner_x + left_w + gap
    c.setFillColor(colors.HexColor("#fef2f2"))
    c.setStrokeColor(red)
    c.setLineWidth(0.75)
    c.roundRect(amt_x, cursor_y - payer_box_h, right_w, payer_box_h, 4, stroke=1, fill=1)
    c.setFillColor(red)
    c.setFont("Homex-Bold", 6.8)
    c.drawString(amt_x + 7, cursor_y - 10, "MONTO RECIBIDO")
    c.setFillColor(dark)
    c.setFont("Homex-Bold", 11.5)
    c.drawRightString(amt_x + right_w - 7, cursor_y - 28, f"{moneda_codigo} {pago_texto}")

    cursor_y -= payer_box_h + 6

    # Fila 2: Monto en letras
    letras_h = 30
    c.setFillColor(pale)
    c.setStrokeColor(border)
    c.setLineWidth(0.5)
    c.roundRect(inner_x, cursor_y - letras_h, inner_w, letras_h, 4, stroke=1, fill=1)
    c.setFillColor(muted)
    c.setFont("Homex-Bold", 6.8)
    c.drawString(inner_x + 7, cursor_y - 10, "SON (MONTO EN LETRAS)")
    _draw_wrapped_paragraph(
        c,
        recibo.monto_en_letras,
        inner_x + 7,
        cursor_y - 12,
        inner_w - 14,
        letras_h - 14,
        font_name="Homex",
        sizes=(8.0, 7.2, 6.6),
    )

    cursor_y -= letras_h + 6

    # Fila 3: Concepto (izq) + Tipo de pago y cheque (der)
    mid_h = 46
    c.setFillColor(pale)
    c.setStrokeColor(border)
    c.roundRect(inner_x, cursor_y - mid_h, left_w, mid_h, 4, stroke=1, fill=1)
    c.setFillColor(muted)
    c.setFont("Homex-Bold", 6.8)
    c.drawString(inner_x + 7, cursor_y - 10, "CONCEPTO")
    _draw_wrapped_paragraph(
        c,
        recibo.concepto,
        inner_x + 7,
        cursor_y - 12,
        left_w - 14,
        mid_h - 15,
        font_name="Homex",
        sizes=(8.2, 7.4, 6.6),
    )

    pay_text = recibo.tipo_pago.nombre
    if recibo.tipo_pago.codigo == "CHEQUE" and (recibo.numero_cheque or recibo.banco):
        pay_text = (
            f"{recibo.tipo_pago.nombre}\n"
            f"Cheque N° {recibo.numero_cheque or '—'} · {recibo.banco or '—'}"
        )
    c.setFillColor(pale)
    c.roundRect(amt_x, cursor_y - mid_h, right_w, mid_h, 4, stroke=1, fill=1)
    c.setFillColor(muted)
    c.setFont("Homex-Bold", 6.8)
    c.drawString(amt_x + 7, cursor_y - 10, "TIPO DE PAGO")
    _draw_wrapped_paragraph(
        c,
        pay_text,
        amt_x + 7,
        cursor_y - 12,
        right_w - 14,
        mid_h - 15,
        font_name="Homex-Bold",
        sizes=(8.0, 7.2, 6.5),
    )

    cursor_y -= mid_h + 6

    # Fila 4: Resumen financiero del pedido (4 columnas)
    fin_h = 34
    c.setFillColor(pale)
    c.setStrokeColor(border)
    c.roundRect(inner_x, cursor_y - fin_h, inner_w, fin_h, 4, stroke=1, fill=1)
    col_w = inner_w / 4
    fin_items = [
        ("PEDIDO", f"Pedido #{recibo.pedido_id}"),
        ("TOTAL PEDIDO", f"{moneda_codigo} {total_texto}"),
        ("ACUMULADO A CUENTA", f"{moneda_codigo} {a_cuenta_texto}"),
        ("SALDO RESTANTE", f"{moneda_codigo} {saldo_texto}"),
    ]
    for idx, (lbl, val) in enumerate(fin_items):
        cx = inner_x + idx * col_w
        if idx > 0:
            c.setStrokeColor(border)
            c.line(cx, cursor_y - 5, cx, cursor_y - fin_h + 5)
        c.setFillColor(muted)
        c.setFont("Homex-Bold", 6.5)
        c.drawString(cx + 7, cursor_y - 11, lbl)
        c.setFillColor(dark)
        c.setFont("Homex-Bold", 8.5)
        c.drawString(cx + 7, cursor_y - 25, val)

    # Fila 5: Dos espacios de firma al pie de la mitad, con espacio inferior libre para nombres
    sig_bottom = y_top - height + pad + 18
    sig_w = (inner_w - 28) / 2
    sig_line_y = sig_bottom + 12

    c.setStrokeColor(grey)
    c.setLineWidth(0.75)
    c.line(inner_x + 8, sig_line_y, inner_x + 8 + sig_w - 16, sig_line_y)
    c.line(
        inner_x + sig_w + 28 + 8,
        sig_line_y,
        inner_x + inner_w - 8,
        sig_line_y,
    )

    c.setFillColor(grey)
    c.setFont("Homex-Bold", 7.8)
    c.drawCentredString(inner_x + sig_w / 2, sig_bottom + 1, "Firma del pagador")
    c.drawCentredString(inner_x + sig_w + 28 + sig_w / 2, sig_bottom + 1, "Recibí conforme")

    # Marca de agua ANULADO si corresponde (preservando todos los datos originales)
    if recibo.estado == "ANULADO":
        c.saveState()
        c.translate(x + width / 2, y_top - height / 2)
        c.rotate(24)
        c.setFillColor(colors.Color(0.725, 0.11, 0.11, alpha=0.18))
        c.setFont("Homex-Bold", 48)
        c.drawCentredString(0, -16, "ANULADO")
        c.restoreState()

    c.restoreState()


def renderizar_recibo_pdf(recibo_id: int, *, usuario) -> bytes:
    """Genera un PDF carta vertical con dos copias idénticas del recibo (cliente y HOMEX)."""
    from apps.documentos.pdf import (
        _es_documento_simulado,
        _exigir_usuario_autenticado,
        _formatear_numero_bo,
        _register_fonts,
        _spanish_date,
    )

    _exigir_usuario_autenticado(usuario)
    _register_fonts()

    recibo = Recibo.objects.select_related(
        "pedido__proforma__moneda",
        "tipo_pago",
    ).get(pk=recibo_id)

    moneda = recibo.pedido.proforma.moneda.codigo
    fecha_texto = _spanish_date(timezone.localdate())
    pago_texto = _formatear_numero_bo(recibo.pago_actual)
    total_texto = _formatear_numero_bo(recibo.total)
    a_cuenta_texto = _formatear_numero_bo(recibo.a_cuenta)
    saldo_texto = _formatear_numero_bo(recibo.saldo)

    logo_path = Path(__file__).resolve().parent / "assets" / "branding" / "logo-pdf.png"

    page_w, page_h = letter  # 612 x 792 pt
    margin_x = 12 * mm
    margin_y = 10 * mm
    usable_w = page_w - 2 * margin_x
    usable_h = page_h - 2 * margin_y
    cut_gap = 22
    half_h = (usable_h - cut_gap) / 2

    output = BytesIO()
    c = Canvas(output, pagesize=letter)
    c.setTitle(f"Recibo #{recibo.numero}")

    # Mitad superior
    top_y = page_h - margin_y
    _draw_recibo_copy(
        c,
        recibo=recibo,
        moneda_codigo=moneda,
        fecha_texto=fecha_texto,
        pago_texto=pago_texto,
        total_texto=total_texto,
        a_cuenta_texto=a_cuenta_texto,
        saldo_texto=saldo_texto,
        x=margin_x,
        y_top=top_y,
        width=usable_w,
        height=half_h,
        logo_path=logo_path,
    )

    # Línea punteada central de separación
    cut_y = top_y - half_h - cut_gap / 2
    c.saveState()
    c.setStrokeColor(colors.HexColor("#94a3b8"))
    c.setLineWidth(0.75)
    c.setDash(4, 3)
    c.line(margin_x, cut_y, page_w - margin_x, cut_y)
    c.restoreState()

    # Mitad inferior
    bottom_top_y = top_y - half_h - cut_gap
    _draw_recibo_copy(
        c,
        recibo=recibo,
        moneda_codigo=moneda,
        fecha_texto=fecha_texto,
        pago_texto=pago_texto,
        total_texto=total_texto,
        a_cuenta_texto=a_cuenta_texto,
        saldo_texto=saldo_texto,
        x=margin_x,
        y_top=bottom_top_y,
        width=usable_w,
        height=half_h,
        logo_path=logo_path,
    )

    es_simulado = _es_documento_simulado(
        "RECIBO", getattr(recibo, "id", None)
    ) or _es_documento_simulado("PROFORMA", getattr(recibo.pedido, "proforma_id", None))
    if es_simulado:
        c.saveState()
        c.setFont("Homex", 6.8)
        c.setFillColor(colors.HexColor("#64748b"))
        c.drawCentredString(
            page_w / 2,
            margin_y - 7,
            "HOMEX · Comprobante oficial de cobro · Documento de demostración (datos simulados)",
        )
        c.restoreState()

    c.showPage()
    c.save()
    return output.getvalue()
