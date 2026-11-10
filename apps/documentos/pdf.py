import logging
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.core.files.storage import default_storage
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus import Image as PdfImage

from apps.documentos.models import ArchivoAdjunto
from apps.documentos.pdf_layout import Columns, ProductCard
from apps.documentos.pdf_technical import fields, present, technical_entries, text
from apps.media.storage import privado
from apps.proformas.models import Proforma


def _texto(valor):
    if valor is None:
        return ""
    return escape(str(valor).strip())


def _formatear_numero_bo(valor, decimales=2):
    if valor is None or valor == "":
        return ""
    try:
        num = Decimal(str(valor))
        if not num.is_finite():
            return _texto(valor)
    except (InvalidOperation, ValueError, TypeError):
        return _texto(valor)
    partes = f"{num:,.{decimales}f}".split(".")
    entero = partes[0].replace(",", ".")
    dec = partes[1] if len(partes) > 1 else ""
    return f"{entero},{dec}" if dec else entero


def _formatear_moneda(valor, codigo_moneda="BOB"):
    if valor is None or valor == "":
        return "-"
    num_str = _formatear_numero_bo(valor, 2)
    if codigo_moneda == "BOB":
        return f"Bs {num_str}"
    if codigo_moneda == "USD":
        return f"$us {num_str}"
    return f"{codigo_moneda} {num_str}"


def _limpiar_conectores(texto: str) -> str:
    """No eliminar preposiciones que pueden formar parte del dato original."""
    return str(texto or "").strip()


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


class NumberedCanvas(pdf_canvas.Canvas):
    """Pie con número actual y total real de páginas."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.saveState()
            ancho, _ = self._pagesize
            self.setStrokeColor(colors.HexColor("#9ca3af"))
            self.setLineWidth(0.45)
            self.line(14 * mm, 13 * mm, ancho - 14 * mm, 13 * mm)
            self.setFillColor(colors.HexColor("#374151"))
            self.setFont("Helvetica", 7.5)
            self.drawString(14 * mm, 9 * mm, "HOMEX · Cotización comercial")
            self.drawRightString(ancho - 14 * mm, 9 * mm, f"Página {self._pageNumber} de {total}")
            self.restoreState()
            super().showPage()
        super().save()


def _imagen_principal_detalle(detalle):
    """Leer portada autorizada; los archivos privados nunca se exponen como URL."""
    clave = None
    almacenamiento = default_storage
    if detalle.producto_id:
        producto = detalle.producto
        imagen = producto.imagenes.order_by("-principal", "posicion", "id").first()
        if imagen:
            clave = imagen.ruta_storage
        elif producto.imagen_principal:
            clave = producto.imagen_principal.name
    else:
        adjunto = (
            ArchivoAdjunto.objects.filter(proforma_detalle_id=detalle.pk)
            .order_by("-principal", "posicion", "id")
            .first()
        )
        if adjunto:
            clave = adjunto.ruta_storage
            almacenamiento = privado() if adjunto.privado else default_storage
    if not clave:
        return None
    try:
        with almacenamiento.open(clave, "rb") as archivo:
            datos = archivo.read(12 * 1024 * 1024 + 1)
        if len(datos) > 12 * 1024 * 1024:
            return None
        with PILImage.open(BytesIO(datos)) as original:
            original.load()
            copia = original.convert("RGB")
            copia.thumbnail((1400, 1400))
            ancho, alto = copia.size
            stream = BytesIO()
            copia.save(stream, format="JPEG", quality=88, optimize=True)
        if not ancho or not alto:
            return None
        max_w, max_h = 44 * mm, 44 * mm
        factor = min(max_w / ancho, max_h / alto)
        stream.seek(0)
        return PdfImage(stream, width=ancho * factor, height=alto * factor)
    except (OSError, ValueError, PILImage.DecompressionBombError):
        return None


def _register_fonts():
    directory = Path(__file__).with_name("fonts")
    if "Homex" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("Homex", str(directory / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("Homex-Bold", str(directory / "DejaVuSans-Bold.ttf")))
        pdfmetrics.registerFontFamily(
            "Homex", normal="Homex", bold="Homex-Bold", italic="Homex", boldItalic="Homex-Bold"
        )


# Import locking makes the font family available atomically to concurrent requests.
_register_fonts()


def _quantity(value):
    # Preserve every stored fractional digit; remove only insignificant zeroes.
    return (
        format(Decimal(str(value)), "f").rstrip("0").rstrip(".").replace(".", ",")
        if "." in format(Decimal(str(value)), "f")
        else str(value)
    )


def _spanish_date(value):
    months = (
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    )
    return f"{value.day} de {months[value.month - 1]} de {value.year}"


def renderizar_proforma_pdf(proforma_id: int, *, usuario) -> bytes:
    """Generate for the verified requesting actor, never the assigned seller.

    HTTP callers must first enforce their existing object permissions. This
    function requires an explicit authenticated actor and cannot accept a user ID.
    It reads persisted commercial amounts without repairing historical records.
    """
    if not getattr(usuario, "is_authenticated", False):
        raise PermissionError("An authenticated requesting user is required.")
    proforma = (
        Proforma.objects.select_related("cliente", "moneda", "estado")
        .prefetch_related(
            "detalles__unidad",
            "detalles__tipo_item",
            "detalles__especificacionmueble__tipo_mueble",
            "detalles__producto__imagenes",
            "detalles__producto__productosilla",
            "detalles__producto__productopiso",
        )
        .get(pk=proforma_id)
    )
    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=letter,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=18 * mm,
        title=f"Proforma - Cotización {proforma.numero}",
    )
    # Frames have 6pt internal padding on each side in SimpleDocTemplate.
    width = letter[0] - 28 * mm - 12
    red, dark = colors.HexColor("#b91c1c"), colors.HexColor("#0f172a")
    grey, border, pale = (colors.HexColor(c) for c in ("#334155", "#d9dee5", "#f8fafc"))
    base = ParagraphStyle(
        "Commercial", fontName="Homex", fontSize=8.3, leading=11.5, textColor=grey
    )
    bold = ParagraphStyle("CommercialBold", parent=base, fontName="Homex-Bold", textColor=dark)
    small = ParagraphStyle("Small", parent=base, fontSize=7, leading=9.5)
    heading = ParagraphStyle(
        "Section",
        parent=bold,
        fontSize=8,
        leading=11,
        spaceBefore=6,
        spaceAfter=5,
        keepWithNext=True,
    )
    technical_heading = ParagraphStyle("TechnicalSection", parent=heading, textColor=red)
    sub = ParagraphStyle("Subsection", parent=bold, fontSize=8.3, leading=11.5, keepWithNext=True)
    right = ParagraphStyle("Right", parent=base, alignment=TA_RIGHT)
    center = ParagraphStyle("Signature", parent=base, alignment=TA_CENTER)
    title_style = ParagraphStyle(
        "QuoteTitle",
        parent=bold,
        fontSize=13.5,
        leading=17,
        spaceBefore=9,
        spaceAfter=8,
        keepWithNext=True,
    )
    chip_style = ParagraphStyle("Dimension", parent=base, fontSize=7.6, leading=10.5)

    def p(value, style=base):
        return Paragraph(text(value), style)

    def table(rows, widths, *, background=None, padding=6):
        t = Table(rows, colWidths=widths, hAlign="LEFT")
        commands = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), padding),
            ("RIGHTPADDING", (0, 0), (-1, -1), padding),
            ("TOPPADDING", (0, 0), (-1, -1), padding),
            ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
        ]
        if background:
            commands += [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("BOX", (0, 0), (-1, -1), 0.4, border),
            ]
        t.setStyle(TableStyle(commands))
        return t

    # Retain the existing institutional monogram and slogan.
    logo_style = ParagraphStyle(
        "Logo", parent=bold, fontSize=16, leading=20, textColor=colors.white, alignment=TA_CENTER
    )
    logo = table([[p("H", logo_style)]], [10 * mm], background=red, padding=4)
    brand = table(
        [
            [
                logo,
                [
                    p("HOMEX", ParagraphStyle("Brand", parent=bold, fontSize=16, leading=19)),
                    p(
                        "DISEÑO & MOBILIARIO",
                        ParagraphStyle("Tagline", parent=small, textColor=red),
                    ),
                ],
            ]
        ],
        [12 * mm, width * 0.58 - 12 * mm],
        padding=0,
    )
    left = [
        brand,
        Spacer(1, 4),
        p("Soluciones integrales de equipamiento corporativo y residencial\nBolivia", small),
    ]
    draft = proforma.estado.codigo == "BORRADOR"
    status = "VISTA PREVIA — NO EMITIDA" if draft else proforma.estado.nombre
    meta_status = ParagraphStyle(
        "Status", parent=small, textColor=red, alignment=TA_RIGHT, fontName="Homex-Bold"
    )
    number_style = ParagraphStyle(
        "Number", parent=bold, fontSize=14, leading=20, alignment=TA_RIGHT
    )
    metadata = [
        p(status, meta_status),
        p(f"N.º {proforma.numero}", number_style),
        p(f"Emisión: {_spanish_date(proforma.fecha)}", right),
    ]
    story = [
        table([[left, metadata]], [width * 0.58, width * 0.42], padding=0),
        HRFlowable(width="100%", thickness=0.8, color=red, spaceBefore=9, spaceAfter=10),
    ]
    customer = _cliente(proforma)
    # Snapshot contact names identify the representative; company names identify the recipient.
    recipient = customer[1] or customer[0] or ""
    boxes = table(
        [
            [
                [p("DATOS DEL CLIENTE", small), p(recipient, bold)],
                [p("TIPO DE DOCUMENTO", small), p("Proforma - Cotización", bold)],
            ]
        ],
        [width / 2, width / 2],
        background=pale,
        padding=8,
    )
    boxes.setStyle(TableStyle([("LINEBEFORE", (1, 0), (1, 0), 0.4, border)]))
    story.append(boxes)
    item_prefix = []
    if present(proforma.titulo):
        item_prefix.append(p(proforma.titulo, title_style))
    if not item_prefix:
        item_prefix.append(Spacer(1, 8))
    currency = proforma.moneda.codigo
    details = sorted(proforma.detalles.all(), key=lambda detail: detail.pk)
    for index, detail in enumerate(details, 1):
        category = detail.tipo_item.nombre if detail.tipo_item_id else ""
        item_header = table(
            [
                [
                    p(f"ÍTEM {index:02d}", bold),
                    p(detail.nombre, bold),
                    p(category, right),
                ]
            ],
            [width * 0.13, width * 0.61, width * 0.26],
            background=pale,
        )
        item_header.setStyle(
            TableStyle([("LINEBEFORE", (1, 0), (2, 0), 0.6, colors.HexColor("#8b9096"))])
        )
        if index == 1:
            # Prefix belongs to the splittable first card, not an oversized KeepTogether.
            item_header = table([[item_prefix + [item_header]]], [width], padding=0)
        contents = []
        if detail.producto_id is None and detail.familia_producto_id is not None:
            contents.append(
                p("Variante pendiente de selección; sin SKU definitivo ni stock reservado", small)
            )
        specification = getattr(detail, "especificacionmueble", None)
        entries = []
        if specification:
            entries = technical_entries(
                specification.datos_tecnicos,
                specification.observaciones,
                detail.descripcion,
                detail.nombre,
            )
            if getattr(specification, "tipo_mueble_id", None):
                furniture_type = specification.tipo_mueble.nombre
                if not entries or entries[0] != ("section", "GENERAL"):
                    entries.insert(0, ("section", "GENERAL"))
                entries.insert(1, ("text", f"<b>Tipo de mueble:</b> {text(furniture_type)}"))
        elif detail.producto_id:
            product = detail.producto
            # Keep catalogue properties; never invent furniture sets for these products.
            entries = [
                ("text", v) for v in fields(product.observaciones, "Observaciones del producto")
            ]
            chair = getattr(product, "productosilla", None)
            floor = getattr(product, "productopiso", None)
            if chair:
                for name in (
                    "marca",
                    "modelo",
                    "color_primario",
                    "color_secundario",
                    "especificaciones",
                ):
                    value = getattr(chair, name)
                    value = getattr(value, "nombre", value)
                    entries.extend(
                        ("text", v) for v in fields(value, name.replace("_", " ").capitalize())
                    )
            if floor:
                for name in (
                    "marca",
                    "modelo",
                    "tipo",
                    "material",
                    "diseno",
                    "espesor_mm",
                    "acabado",
                    "largo_mm",
                    "ancho_mm",
                    "m2_por_caja",
                ):
                    value = getattr(floor, name)
                    value = getattr(value, "nombre", value)
                    entries.extend(
                        ("text", v) for v in fields(value, name.replace("_", " ").capitalize())
                    )
        if present(detail.descripcion) and not specification:
            contents.append(p(detail.descripcion))

        def flow_entries(items):
            flows = []
            for kind, value in items:
                if kind in ("dimensions", "characteristics"):
                    count = 3 if kind == "dimensions" else 2
                    for offset in range(0, len(value), count):
                        cells = value[offset : offset + count]
                        flows.append(
                            Columns(
                                [[Paragraph(v, chip_style)] for v in cells]
                                + [[] for _ in range(count - len(cells))]
                            )
                        )
                elif kind == "groups":
                    for offset in range(0, len(value), 2):
                        flows.append(
                            Columns([flow_entries(group) for group in value[offset : offset + 2]])
                        )
                else:
                    flows.append(
                        Paragraph(
                            value,
                            technical_heading
                            if kind == "section"
                            else sub
                            if kind == "subsection"
                            else base,
                        )
                    )
            return flows

        image = _imagen_principal_detalle(detail)
        # Only GENERAL shares the photograph's upper zone. All later sections
        # use the entire document width, including on continuation pages.
        boundary = next(
            (
                i
                for i, entry in enumerate(entries)
                if entry[0] == "section" and entry[1] != "GENERAL"
            ),
            len(entries),
        )
        general_flows = flow_entries(entries[:boundary])
        if image:
            contents.append(
                Columns([[image], general_flows], [50 * mm, width - 50 * mm], center_first=True)
            )
        else:
            contents.extend(general_flows)
        contents.extend(flow_entries(entries[boundary:]))
        amount_label, amount = (
            ("Importe total negociado", detail.importe_negociado)
            if detail.modo_calculo == "TOTAL_NEGOCIADO"
            else ("Precio unitario", detail.precio_unitario)
        )
        economic = [
            ("Cantidad", f"{_quantity(detail.cantidad)} {detail.unidad.nombre}"),
            (amount_label, _formatear_moneda(amount, currency)),
        ]
        if detail.descuento != 0:
            economic.append(("Descuento", _formatear_moneda(detail.descuento, currency)))
        economic.append(("Subtotal", _formatear_moneda(detail.total, currency)))
        footer = table(
            [
                [
                    [
                        p(
                            k,
                            ParagraphStyle("EconomicLabel", parent=small, alignment=TA_RIGHT)
                            if k == "Subtotal"
                            else small,
                        ),
                        p(
                            v,
                            ParagraphStyle("EconomicAmount", parent=bold, alignment=TA_RIGHT)
                            if k == "Subtotal"
                            else bold,
                        ),
                    ]
                    for k, v in economic
                ]
            ],
            [width / len(economic)] * len(economic),
            background=pale,
        )
        footer.setStyle(TableStyle([("RIGHTPADDING", (-1, 0), (-1, 0), 0)]))
        story.append(ProductCard(item_header, None, contents, footer))

    if not details:
        story.extend(item_prefix)

    # Report historical incompatibility without changing or recalculating displayed amounts.
    if sum((detail.total for detail in details), Decimal(0)) != proforma.total:
        logging.getLogger(__name__).warning(
            "Persisted proforma total differs from line totals: id=%s", proforma_id
        )
    total_style = ParagraphStyle(
        "Total", parent=bold, fontSize=14, leading=19, alignment=TA_RIGHT, textColor=red
    )
    total = table(
        [[p("TOTAL COTIZADO", bold), p(_formatear_moneda(proforma.total, currency), total_style)]],
        [width * 0.5, width * 0.5],
        padding=8,
    )
    total.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, -1), 0.6, border)]))
    story.append(total)
    if present(proforma.observaciones):
        story += [p("OBSERVACIONES DE LA PROFORMA", heading), p(proforma.observaciones)]

    conditions = []
    if present(proforma.porcentaje_adelanto):
        conditions.append(("ANTICIPO REQUERIDO", f"{_quantity(proforma.porcentaje_adelanto)} %"))
    if present(proforma.plazo_entrega):
        conditions.append(("PLAZO DE ENTREGA", proforma.plazo_entrega))
    if present(proforma.validez_oferta):
        conditions.append(("VALIDEZ DE LA OFERTA", f"{proforma.validez_oferta} días"))
    if conditions:
        story += [
            p("CONDICIONES COMERCIALES", heading),
            table(
                [[[p(k, small), p(v, bold)] for k, v in conditions]],
                [width / len(conditions)] * len(conditions),
                background=pale,
                padding=8,
            ),
        ]

    seller = usuario.get_full_name() or usuario.get_username()
    # Historical companies without a contact do not acquire a fabricated representative.
    representative = customer[0] or ""
    signatures = table(
        [
            ["", "", ""],
            [
                [
                    p(seller, center),
                    Paragraph("<b>Firma autorizada</b>", center),
                    Paragraph("<b>Depto. de ventas</b>", center),
                ],
                "",
                [p(representative, center), Paragraph("<b>Firma del cliente</b>", center)],
            ],
        ],
        [(width - 12 * mm) / 2, 12 * mm, (width - 12 * mm) / 2],
        padding=0,
    )
    signatures._argH[0] = 27 * mm
    signatures.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (0, 0), 0.5, dark),
                ("LINEBELOW", (2, 0), (2, 0), 0.5, dark),
                ("TOPPADDING", (0, 1), (-1, 1), 5),
            ]
        )
    )
    story.append(KeepTogether([Spacer(1, 5 * mm), signatures]))
    doc.build(story, canvasmaker=NumberedCanvas)
    return output.getvalue()
