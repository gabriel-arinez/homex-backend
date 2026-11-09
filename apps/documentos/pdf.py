from decimal import Decimal, InvalidOperation
from io import BytesIO
from xml.sax.saxutils import escape

from django.core.files.storage import default_storage
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    CondPageBreak,
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


def _construir_ficha_tecnica(datos_tecnicos, observaciones, estilos, estilo_texto, estilo_sub):
    """Estructura la ficha técnica de forma humana, adaptativa y limpia sin volcados JSON."""
    if not isinstance(datos_tecnicos, dict):
        datos_tecnicos = {}

    generales = datos_tecnicos.get("caracteristicas_generales") or {}
    if not isinstance(generales, dict):
        generales = {}
    raw_dims = generales.get("dimensiones") or {}

    dims_list = []
    if isinstance(raw_dims, dict):
        for k, v in raw_dims.items():
            if isinstance(v, dict):
                val = v.get("valor", "")
                unid = v.get("unidad", "")
                if val:
                    val_bo = _formatear_numero_bo(val, 2)
                    dims_list.append(
                        f"<b>{k.replace('_', ' ').capitalize()}:</b> {val_bo} {unid}".strip()
                    )
            elif v not in (None, ""):
                val_bo = _formatear_numero_bo(v, 2)
                dims_list.append(f"<b>{k.replace('_', ' ').capitalize()}:</b> {val_bo}")

    atributos_generales = []
    for atributo in generales.get("atributos", []) or []:
        if not isinstance(atributo, dict):
            continue
        nombre, valor = atributo.get("nombre"), atributo.get("valor")
        if nombre and valor not in (None, ""):
            unidad = atributo.get("unidad") or ""
            atributos_generales.append(
                f"<b>{_texto(nombre)}:</b> {_texto(valor)} {_texto(unidad)}".strip()
            )

    materiales = []
    if generales.get("material"):
        materiales.append(str(generales["material"]))
    componentes = []
    for c in datos_tecnicos.get("componentes", []) or []:
        if isinstance(c, dict) and c.get("nombre"):
            nombre_c = c["nombre"].capitalize()
            detalles_c = []
            if c.get("cantidad_interna") and int(c.get("cantidad_interna", 1)) > 1:
                detalles_c.append(f"{c['cantidad_interna']} pzas")
            if c.get("material"):
                detalles_c.append(c["material"])
                if c["material"] not in materiales:
                    materiales.append(c["material"])
            if c.get("espesor"):
                detalles_c.append(f"Espesor {c['espesor']}")
            if c.get("color"):
                detalles_c.append(c["color"])
            if c.get("dimensiones"):
                detalles_c.append(c["dimensiones"])
            if c.get("acabado"):
                detalles_c.append(f"Acabado {c['acabado']}")
            for atributo in c.get("atributos", []) or []:
                if isinstance(atributo, dict) and atributo.get("nombre") and atributo.get("valor"):
                    detalles_c.append(
                        f"{atributo['nombre']}: {atributo['valor']} "
                        f"{atributo.get('unidad') or ''}".strip()
                    )
            desc_c = f"• <b>{_texto(nombre_c)}</b>"
            if detalles_c:
                desc_c += f": {_texto(' · '.join(detalles_c))}"
            componentes.append(desc_c)

    accesorios = []
    for acc in datos_tecnicos.get("accesorios", []) or []:
        if isinstance(acc, str) and acc.strip():
            limpio = _limpiar_conectores(acc)
            if limpio and limpio not in accesorios:
                accesorios.append(_texto(limpio))

    lineas_ficha = []
    if dims_list:
        lineas_ficha.append(f"<b>Dimensiones:</b> {' · '.join(dims_list)}")
    if materiales:
        lineas_ficha.append(f"<b>Materialidad:</b> {_texto(' · '.join(materiales))}")
    if atributos_generales:
        lineas_ficha.append("<b>Características:</b> " + " · ".join(atributos_generales))
    conjuntos = [
        _texto(c.get("nombre")) for c in datos_tecnicos.get("conjuntos", []) or []
        if isinstance(c, dict) and c.get("nombre")
    ]
    if conjuntos:
        lineas_ficha.append(f"<b>Conjuntos:</b> {' · '.join(conjuntos)}")
    if accesorios:
        lineas_ficha.append(f"<b>Accesorios y herrajes:</b> {', '.join(accesorios)}")
    if componentes:
        lineas_ficha.append("<b>Componentes estructurados:</b><br/>" + "<br/>".join(componentes))

    if observaciones:
        obs_limpia = _limpiar_conectores(str(observaciones))
        if obs_limpia:
            lineas_ficha.append(f"<b>Observaciones técnicas:</b> <i>{_texto(obs_limpia)}</i>")

    # Si no hubo componentes estructurados pero hay advertencias
    advertencias = datos_tecnicos.get("advertencias") or []
    if advertencias:
        adv_limpias = [_limpiar_conectores(str(a)) for a in advertencias if a]
        lineas_ficha.append(
            f"<b>Notas de fabricación:</b> <i>{_texto(' · '.join(adv_limpias))}</i>"
        )

    return lineas_ficha


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


def renderizar_proforma_pdf(proforma_id: int) -> bytes:
    proforma = (
        Proforma.objects.select_related("cliente", "moneda", "estado", "vendedor")
        .prefetch_related(
            "detalles__unidad",
            "detalles__tipo_item",
            "detalles__especificacionmueble",
            "detalles__producto__imagenes",
        )
        .get(pk=proforma_id)
    )
    salida = BytesIO()
    # Tamaño Carta vertical: 8.5 x 11 pulgadas (215.9 x 279.4 mm)
    doc = SimpleDocTemplate(
        salida,
        pagesize=letter,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=f"#{proforma.numero}",
    )
    ancho_util = letter[0] - (28 * mm)

    estilos = getSampleStyleSheet()
    rojo_homex = colors.HexColor("#dc2626")
    gris_oscuro = colors.HexColor("#0f172a")
    gris_texto = colors.HexColor("#334155")
    gris_borde = colors.HexColor("#cbd5e1")
    gris_fondo = colors.HexColor("#f8fafc")

    titulo_marca = ParagraphStyle(
        "HOMEX_Marca",
        parent=estilos["Normal"],
        fontSize=15,
        leading=17,
        fontName="Helvetica-Bold",
        textColor=gris_oscuro,
    )
    tagline_marca = ParagraphStyle(
        "HOMEX_Tagline",
        parent=estilos["Normal"],
        fontSize=7,
        leading=9,
        fontName="Helvetica-Bold",
        textColor=rojo_homex,
    )
    direccion_style = ParagraphStyle(
        "Direccion",
        parent=estilos["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#374151"),
    )
    meta_kicker = ParagraphStyle(
        "MetaKicker",
        parent=estilos["Normal"],
        alignment=TA_RIGHT,
        fontSize=7.5,
        leading=9,
        fontName="Helvetica-Bold",
        textColor=rojo_homex,
    )
    meta_numero = ParagraphStyle(
        "MetaNumero",
        parent=estilos["Normal"],
        alignment=TA_RIGHT,
        fontSize=15,
        leading=17,
        fontName="Helvetica-Bold",
        textColor=gris_oscuro,
    )
    meta_texto = ParagraphStyle(
        "MetaTexto",
        parent=estilos["Normal"],
        alignment=TA_RIGHT,
        fontSize=8,
        leading=10,
        textColor=gris_texto,
    )
    bloque_titulo = ParagraphStyle(
        "BloqueTitulo",
        parent=estilos["Normal"],
        fontSize=7.5,
        leading=9,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#374151"),
    )
    pequeno = ParagraphStyle(
        "Pequeno",
        parent=estilos["Normal"],
        fontSize=8.5,
        leading=11,
        textColor=gris_texto,
    )
    pequeno_negrita = ParagraphStyle(
        "PequenoNegrita",
        parent=pequeno,
        fontName="Helvetica-Bold",
        textColor=gris_oscuro,
    )
    derecha = ParagraphStyle("Derecha", parent=pequeno, alignment=TA_RIGHT)
    derecha_negrita = ParagraphStyle("DerechaNegrita", parent=pequeno_negrita, alignment=TA_RIGHT)

    estado_cod = getattr(proforma.estado, "codigo", "BORRADOR") if proforma.estado else "BORRADOR"
    es_borrador = estado_cod == "BORRADOR"

    # Encabezado institucional
    kicker_texto = "VISTA PREVIA — NO EMITIDA" if es_borrador else "PROFORMA – COTIZACIÓN"
    num_texto = f"N.º {_texto(proforma.numero)}" if proforma.numero else "Borrador"

    estilo_logo = ParagraphStyle(
        "LogoH", parent=estilos["Normal"], alignment=TA_CENTER,
        textColor=colors.white, fontName="Helvetica-Bold", fontSize=15, leading=18,
    )
    cuadro_logo = Table(
        [[Paragraph("H", estilo_logo)]], colWidths=[10 * mm], rowHeights=[10 * mm]
    )
    cuadro_logo.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), rojo_homex),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    marca_cabecera = Table(
        [[
            cuadro_logo,
            [Paragraph("<b>HOMEX</b>", titulo_marca),
             Paragraph("DISEÑO & MOBILIARIO", tagline_marca)],
        ]],
        colWidths=[12 * mm, ancho_util * 0.6 - 12 * mm],
    )
    marca_cabecera.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    col_marca = [
        marca_cabecera,
        Spacer(1, 1.5 * mm),
        Paragraph(
            "Soluciones integrales de equipamiento corporativo y residencial<br/>Bolivia",
            direccion_style,
        ),
    ]
    col_meta = [
        Paragraph(kicker_texto, meta_kicker),
        Paragraph(num_texto, meta_numero),
        Paragraph(f"<b>Emisión:</b> {_texto(proforma.fecha)}", meta_texto),
    ]
    if proforma.validez_oferta:
        col_meta.append(
            Paragraph(f"<b>Validez:</b> {proforma.validez_oferta} días calendario", meta_texto)
        )

    tabla_top = Table(
        [[col_marca, col_meta]],
        colWidths=[ancho_util * 0.6, ancho_util * 0.4],
    )
    tabla_top.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    divisor_rojo = HRFlowable(
        width="100%",
        thickness=1.5,
        color=rojo_homex,
        spaceBefore=3 * mm,
        spaceAfter=4 * mm,
    )

    # Bloques de Cliente y Cotización
    datos_cliente = [valor for valor in _cliente(proforma) if valor]
    cliente_lineas = [Paragraph("DATOS DEL CLIENTE", bloque_titulo), Spacer(1, 1.5 * mm)]
    if datos_cliente:
        cliente_lineas.append(Paragraph(f"<b>{_texto(datos_cliente[0])}</b>", pequeno_negrita))
        for d in datos_cliente[1:]:
            cliente_lineas.append(Paragraph(_texto(d), pequeno))
    else:
        cliente_lineas.append(Paragraph("<i>Cliente sin asignar (Provisional)</i>", pequeno))

    cotiz_lineas = [Paragraph("DATOS DE LA COTIZACIÓN", bloque_titulo), Spacer(1, 1.5 * mm)]
    if proforma.titulo:
        cotiz_lineas.append(Paragraph(f"<b>Referencia:</b> {_texto(proforma.titulo)}", pequeno))
    cod_moneda = getattr(proforma.moneda, "codigo", "BOB") if proforma.moneda else "BOB"
    nom_moneda = (
        getattr(proforma.moneda, "nombre", "Bolivianos") if proforma.moneda else "Bolivianos"
    )
    cotiz_lineas.append(Paragraph(f"<b>Moneda:</b> {cod_moneda} ({nom_moneda})", pequeno))
    cotiz_lineas.append(
        Paragraph(
            f"<b>Estado:</b> {_texto(proforma.estado.nombre if proforma.estado else 'Borrador')}",
            pequeno,
        )
    )
    if proforma.plazo_entrega:
        cotiz_lineas.append(
            Paragraph(f"<b>Plazo estimado:</b> {_texto(proforma.plazo_entrega)}", pequeno)
        )

    tabla_bloques = Table(
        [[cliente_lineas, cotiz_lineas]],
        colWidths=[(ancho_util - 4 * mm) / 2, (ancho_util - 4 * mm) / 2],
    )
    tabla_bloques.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), gris_fondo),
                ("BOX", (0, 0), (-1, -1), 0.5, gris_borde),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )

    contenido = [tabla_top, divisor_rojo, tabla_bloques, Spacer(1, 4 * mm)]

    # Fichas visuales comerciales; la fotografía pertenece siempre a esta línea.
    contenido.append(Paragraph("DETALLE DE PRODUCTOS Y ESPECIFICACIONES TÉCNICAS", bloque_titulo))
    contenido.append(Spacer(1, 2 * mm))
    ficha_titulo = ParagraphStyle(
        "FichaTitulo",
        parent=pequeno_negrita,
        fontSize=10.5,
        leading=13,
    )
    ficha_nota = ParagraphStyle(
        "FichaNota",
        parent=pequeno,
        fontSize=8,
        leading=10,
    )

    for indice, detalle in enumerate(proforma.detalles.all(), 1):
        contenido.append(CondPageBreak(60 * mm))
        etiqueta_tipo = detalle.tipo_item.nombre if detalle.tipo_item_id else "Producto"
        cabecera_item = Table(
            [
                [
                    Paragraph(
                        f"<font color='#b91c1c'><b>ÍTEM {indice:02d}</b></font>"
                        f" &nbsp; {_texto(detalle.nombre)}",
                        ficha_titulo,
                    ),
                    Paragraph(_texto(etiqueta_tipo), derecha),
                ]
            ],
            colWidths=[ancho_util * 0.75, ancho_util * 0.25],
        )
        cabecera_item.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
                    ("BOX", (0, 0), (-1, -1), 0.5, gris_borde),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )

        portada = _imagen_principal_detalle(detalle)
        foto = [portada] if portada else [Paragraph("Imagen de referencia pendiente", ficha_nota)]
        especificaciones = []
        if detalle.descripcion:
            especificaciones.append(Paragraph(_texto(detalle.descripcion), pequeno))
        if detalle.producto_id is None and detalle.familia_producto_id is not None:
            especificaciones.append(
                Paragraph("Variante pendiente de selección; sin SKU definitivo", ficha_nota)
            )
        especificacion = getattr(detalle, "especificacionmueble", None)
        if especificacion:
            for texto in _construir_ficha_tecnica(
                especificacion.datos_tecnicos,
                especificacion.observaciones,
                estilos,
                pequeno,
                pequeno_negrita,
            ):
                especificaciones.append(Paragraph(texto, pequeno))
        if not especificaciones:
            especificaciones.append(Paragraph("Sin especificaciones adicionales", ficha_nota))

        # Un bloque inicial compacto mantiene la fotografía junto a la identidad;
        # los apartados restantes fluyen entre páginas sin bloquear una fila gigante.
        cuerpo = Table(
            [[foto, especificaciones[:3]]],
            colWidths=[49 * mm, ancho_util - 49 * mm],
            splitInRow=1,
        )
        cuerpo.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.5, gris_borde),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ]
            )
        )
        contenido.append(cabecera_item)
        contenido.append(cuerpo)
        for extra in especificaciones[3:]:
            contenido.extend([extra, Spacer(1, 1.5 * mm)])

        cantidad_decimal = Decimal(str(detalle.cantidad))
        cantidad = _formatear_numero_bo(
            detalle.cantidad,
            0 if cantidad_decimal == cantidad_decimal.to_integral_value() else 4,
        )
        unidad_nombre = detalle.unidad.nombre if detalle.unidad_id else "Pieza"
        if detalle.modo_calculo == "TOTAL_NEGOCIADO":
            precio_etiqueta = "Importe acordado"
            precio = _formatear_moneda(detalle.importe_negociado, cod_moneda)
        else:
            precio_etiqueta = "Precio unitario"
            precio = _formatear_moneda(detalle.precio_unitario, cod_moneda)
        fila_importes = [
            Paragraph(f"<b>Cantidad:</b> {cantidad} {_texto(unidad_nombre)}", pequeno),
            Paragraph(f"<b>{precio_etiqueta}:</b> {precio}", pequeno),
            Paragraph(
                f"<b>Descuento:</b> {_formatear_moneda(detalle.descuento, cod_moneda)}",
                pequeno,
            ),
            Paragraph(
                f"<b>Subtotal ítem:</b> {_formatear_moneda(detalle.total, cod_moneda)}",
                derecha_negrita,
            ),
        ]
        precios = Table(
            [fila_importes],
            colWidths=[
                ancho_util * 0.22,
                ancho_util * 0.29,
                ancho_util * 0.22,
                ancho_util * 0.27,
            ],
        )
        precios.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), gris_fondo),
                    ("BOX", (0, 0), (-1, -1), 0.5, gris_borde),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        contenido.extend([precios, Spacer(1, 4 * mm)])

    # Resumen Económico
    lineas_totales = [
        ["Subtotal general:", _formatear_moneda(proforma.subtotal, cod_moneda)],
    ]
    if proforma.descuento_total and proforma.descuento_total > 0:
        lineas_totales.append(
            ["Descuento global:", f"-{_formatear_moneda(proforma.descuento_total, cod_moneda)}"]
        )
    lineas_totales.append([f"TOTAL {cod_moneda}:", _formatear_moneda(proforma.total, cod_moneda)])

    tabla_totales = Table(
        lineas_totales,
        colWidths=[38 * mm, 32 * mm],
        hAlign="RIGHT",
    )
    tabla_totales.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, -1), (-1, -1), 10.5),
                ("TEXTCOLOR", (0, -1), (-1, -1), rojo_homex),
                ("LINEABOVE", (0, -1), (-1, -1), 1.2, rojo_homex),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )

    # Condiciones comerciales fidedignas (sin inventar textos)
    condiciones_bloque = []
    if proforma.porcentaje_adelanto is not None:
        condiciones_bloque.append(f"<b>Anticipo requerido:</b> {proforma.porcentaje_adelanto}%")
    if proforma.plazo_entrega:
        condiciones_bloque.append(f"<b>Plazo de entrega:</b> {_texto(proforma.plazo_entrega)}")
    if proforma.validez_oferta is not None:
        condiciones_bloque.append(
            f"<b>Validez de la oferta:</b> {proforma.validez_oferta} días calendario"
        )
    if proforma.observaciones:
        condiciones_bloque.append(
            f"<b>Observaciones generales:</b> {_texto(proforma.observaciones)}"
        )

    bloque_cierre = []
    if condiciones_bloque:
        bloque_cierre.extend(
            [
                Paragraph("CONDICIONES COMERCIALES", bloque_titulo),
                Spacer(1, 1.5 * mm),
                Paragraph(" · ".join(condiciones_bloque), pequeno),
                Spacer(1, 6 * mm),
            ]
        )

    # Firmas
    vendedor_nom = proforma.vendedor.get_full_name() if proforma.vendedor else "HOMEX MOBILIARIO"
    cliente_nom = datos_cliente[0] if datos_cliente else "Aceptación del Cliente"

    col_firma_vendedor = [
        Paragraph(f"<b>{_texto(vendedor_nom or 'HOMEX MOBILIARIO')}</b>", pequeno_negrita),
        Paragraph("Asesor Comercial Autorizado", pequeno),
    ]
    col_firma_cliente = [
        Paragraph(f"<b>{_texto(cliente_nom)}</b>", pequeno_negrita),
        Paragraph("Aceptación y Aprobación Comercial", pequeno),
    ]

    tabla_firmas = Table(
        [
            ["", ""],
            [col_firma_vendedor, col_firma_cliente],
        ],
        colWidths=[ancho_util / 2, ancho_util / 2],
    )
    tabla_firmas.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEABOVE", (0, 0), (0, 0), 0.75, gris_oscuro),
                ("LINEABOVE", (1, 0), (1, 0), 0.75, gris_oscuro),
                ("TOPPADDING", (0, 1), (-1, 1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (-1, -1), 25),
                ("RIGHTPADDING", (0, 0), (-1, -1), 25),
            ]
        )
    )

    # El resumen no se divide, pero las condiciones largas sí pueden paginar.
    contenido.append(KeepTogether([tabla_totales, Spacer(1, 4 * mm)]))
    contenido.extend(bloque_cierre)
    contenido.append(KeepTogether([tabla_firmas]))

    doc.build(contenido, canvasmaker=NumberedCanvas)
    return salida.getvalue()
