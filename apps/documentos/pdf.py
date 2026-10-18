from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.proformas.models import Proforma


def _texto(valor):
    return escape(str(valor if valor is not None else ""))


def _cliente(proforma):
    if proforma.cliente_nombre_snapshot or proforma.cliente_empresa_snapshot:
        return [
            proforma.cliente_nombre_snapshot,
            proforma.cliente_empresa_snapshot,
            proforma.cliente_celular_snapshot,
            proforma.cliente_direccion_snapshot,
        ]
    if proforma.cliente_id:
        cliente = proforma.cliente
        nombre = " ".join(filter(None, [cliente.nombres, cliente.apellidos]))
        return [nombre, cliente.empresa, cliente.celular, cliente.direccion]
    return [
        proforma.prospecto_nombre,
        proforma.prospecto_empresa,
        proforma.prospecto_celular,
        proforma.prospecto_direccion,
    ]


def _descripcion_linea(detalle):
    descripcion = f"<b>{_texto(detalle.nombre)}</b>"
    if detalle.descripcion:
        descripcion += f"<br/>{_texto(detalle.descripcion)}"
    if detalle.producto_id is None and detalle.familia_producto_id is not None:
        descripcion += (
            "<br/><i>Variante pendiente de selección; sin SKU definitivo ni stock reservado</i>"
        )
    return descripcion


def _pares_json(valor, prefijo=""):
    if isinstance(valor, dict):
        for clave, contenido in valor.items():
            etiqueta = f"{prefijo} · {clave}" if prefijo else str(clave)
            yield from _pares_json(contenido, etiqueta)
    elif isinstance(valor, list):
        for indice, contenido in enumerate(valor, 1):
            yield from _pares_json(contenido, f"{prefijo} {indice}")
    elif valor not in (None, "", [], {}):
        yield prefijo.replace("_", " ").capitalize(), valor


def renderizar_proforma_pdf(proforma_id: int) -> bytes:
    proforma = (
        Proforma.objects.select_related("cliente", "moneda")
        .prefetch_related(
            "detalles__unidad", "detalles__tipo_item", "detalles__especificacionmueble"
        )
        .get(pk=proforma_id)
    )
    salida = BytesIO()
    doc = SimpleDocTemplate(
        salida,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=f"Proforma {proforma.numero}",
    )
    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle(
        "HOMEX",
        parent=estilos["Title"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#17324d"),
        spaceAfter=4,
    )
    subtitulo = ParagraphStyle(
        "Subtitulo",
        parent=estilos["Heading2"],
        alignment=TA_CENTER,
        fontSize=11,
        textColor=colors.HexColor("#42647f"),
    )
    pequeno = ParagraphStyle("Pequeno", parent=estilos["BodyText"], fontSize=8.5, leading=11)
    derecha = ParagraphStyle("Derecha", parent=pequeno, alignment=TA_RIGHT)
    contenido = [
        Paragraph("HOMEX", titulo),
        Paragraph(f"PROFORMA N.º {_texto(proforma.numero)}", subtitulo),
        Spacer(1, 5 * mm),
    ]
    datos_cliente = [valor for valor in _cliente(proforma) if valor]
    cabecera = [
        [Paragraph("Fecha", pequeno), Paragraph(_texto(proforma.fecha), pequeno)],
        [
            Paragraph("Cliente", pequeno),
            Paragraph(
                "<br/>".join(_texto(v) for v in datos_cliente)
                if datos_cliente
                else "Sin cliente informado",
                pequeno,
            ),
        ],
    ]
    if proforma.titulo:
        cabecera.append(
            [Paragraph("Referencia", pequeno), Paragraph(_texto(proforma.titulo), pequeno)]
        )
    tabla_cabecera = Table(cabecera, colWidths=[35 * mm, 135 * mm])
    tabla_cabecera.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef3f7")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#9fb2c1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd6df")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    contenido += [tabla_cabecera, Spacer(1, 5 * mm)]
    filas = [
        [
            Paragraph("Descripción", pequeno),
            Paragraph("Cantidad", pequeno),
            Paragraph("P. unitario", derecha),
            Paragraph("Descuento", derecha),
            Paragraph("Total", derecha),
        ]
    ]
    detalles_tecnicos = []
    for indice, detalle in enumerate(proforma.detalles.all(), 1):
        descripcion = _descripcion_linea(detalle)
        filas.append(
            [
                Paragraph(descripcion, pequeno),
                Paragraph(f"{_texto(detalle.cantidad)} {_texto(detalle.unidad.nombre)}", pequeno),
                Paragraph(
                    "Importe negociado: " + _texto(detalle.importe_negociado)
                    if detalle.modo_calculo == "TOTAL_NEGOCIADO"
                    else _texto(detalle.precio_unitario),
                    derecha,
                ),
                Paragraph(_texto(detalle.descuento), derecha),
                Paragraph(_texto(detalle.total), derecha),
            ]
        )
        especificacion = getattr(detalle, "especificacionmueble", None)
        if especificacion:
            pares = list(_pares_json(especificacion.datos_tecnicos))
            if especificacion.observaciones:
                pares.append(("Observaciones", especificacion.observaciones))
            if pares:
                cuerpo = "<br/>".join(f"<b>{_texto(k)}:</b> {_texto(v)}" for k, v in pares)
                detalles_tecnicos.extend(
                    [
                        Paragraph(
                            f"Especificaciones — ítem {indice}: {_texto(detalle.nombre)}",
                            estilos["Heading3"],
                        ),
                        Paragraph(cuerpo, pequeno),
                        Spacer(1, 3 * mm),
                    ]
                )
    tabla = Table(
        filas,
        colWidths=[75 * mm, 28 * mm, 25 * mm, 22 * mm, 25 * mm],
        repeatRows=1,
        splitInRow=1,
    )
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#b7c5cf")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fa")]),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    contenido += [tabla, Spacer(1, 4 * mm)]
    totales = Table(
        [
            ["Subtotal", proforma.subtotal],
            ["Descuentos", proforma.descuento_total],
            [f"TOTAL {proforma.moneda.codigo}", proforma.total],
        ],
        colWidths=[40 * mm, 35 * mm],
        hAlign="RIGHT",
    )
    totales.setStyle(
        TableStyle(
            [
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#17324d")),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    contenido += [totales, Spacer(1, 5 * mm), *detalles_tecnicos]
    condiciones = []
    if proforma.plazo_entrega:
        condiciones.append(("Plazo de entrega", proforma.plazo_entrega))
    if proforma.validez_oferta is not None:
        condiciones.append(("Validez", f"{proforma.validez_oferta} días"))
    if proforma.porcentaje_adelanto is not None:
        condiciones.append(("Adelanto", f"{proforma.porcentaje_adelanto}%"))
    if proforma.observaciones:
        condiciones.append(("Observaciones", proforma.observaciones))
    if condiciones:
        contenido += [
            Paragraph("Condiciones", estilos["Heading2"]),
            Paragraph(
                "<br/>".join(f"<b>{_texto(k)}:</b> {_texto(v)}" for k, v in condiciones), pequeno
            ),
        ]
    doc.build(contenido)
    return salida.getvalue()
