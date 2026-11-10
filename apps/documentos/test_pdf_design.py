"""Approved commercial PDF contract; isolated fixtures, never real quotations."""

from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import pytest
from reportlab.platypus import Paragraph

from apps.documentos.pdf import renderizar_proforma_pdf


def actor(name="Beatriz Solicitante"):
    return NS(is_authenticated=True, get_full_name=lambda: name, get_username=lambda: "actor")


def quote(details=(), **changes):
    fields = dict(
        numero=7300,
        fecha=date(2026, 10, 23),
        titulo="Equipamiento Dirección",
        estado=NS(codigo="BORRADOR", nombre="Borrador"),
        moneda=NS(codigo="BOB"),
        cliente_id=None,
        cliente_nombre_snapshot="Ana Representante",
        cliente_empresa_snapshot="Empresa Histórica",
        cliente_celular_snapshot="NO PUBLICAR",
        cliente_direccion_snapshot="DIRECCIÓN PRIVADA",
        prospecto_nombre=None,
        prospecto_empresa=None,
        prospecto_celular=None,
        prospecto_direccion=None,
        vendedor=actor("Creador Original"),
        detalles=NS(all=lambda: list(details)),
        total=Decimal("7300.00"),
        subtotal=Decimal("9900"),
        descuento_total=Decimal("2600"),
        observaciones="Primera condición registrada.\n\nSegunda condición & montaje <especial>.",
        porcentaje_adelanto=Decimal("50"),
        plazo_entrega="A coordinar con producción",
        validez_oferta=15,
    )
    fields.update(changes)
    return NS(**fields)


def line(data=None, **changes):
    fields = dict(
        pk=1,
        nombre="escritorio Ejecutivo",
        descripcion="Descripción íntegra & original.",
        producto_id=None,
        familia_producto_id=None,
        tipo_item_id=1,
        tipo_item=NS(nombre="Mueble a medida"),
        cantidad=Decimal("1.2345"),
        unidad=NS(nombre="Pieza"),
        modo_calculo="PRECIO_UNITARIO",
        precio_unitario=Decimal("7500.00"),
        importe_negociado=None,
        descuento=Decimal("200"),
        total=Decimal("7300.00"),
        especificacionmueble=NS(
            datos_tecnicos=data or {}, observaciones="Nota técnica completa.", tipo_mueble_id=None
        ),
    )
    fields.update(changes)
    return NS(**fields)


def render(proforma, requester=None, image_factory=None):
    query = Mock()
    query.select_related.return_value = query
    query.prefetch_related.return_value = query
    query.get.return_value = proforma
    texts = []

    def paragraph(text, *args, **kwargs):
        texts.append(text)
        return Paragraph(text, *args, **kwargs)

    with (
        patch("apps.documentos.pdf.Proforma.objects", query),
        patch(
            "apps.documentos.pdf._imagen_principal_detalle",
            side_effect=image_factory or (lambda _: None),
        ),
        patch("apps.documentos.pdf.Paragraph", side_effect=paragraph),
    ):
        pdf = renderizar_proforma_pdf(proforma.numero, usuario=requester or actor())
    return pdf, "\n".join(texts)


def test_header_closing_and_persisted_economics():
    pdf, text = render(quote([line()]))
    assert pdf.startswith(b"%PDF")
    assert b"/MediaBox [ 0 0 612 792 ]" in pdf
    assert "23 de octubre de 2026" in text
    assert "2026-10-23" not in text
    assert "Empresa Histórica" in text and "Ana Representante" in text
    assert "NO PUBLICAR" not in text and "DIRECCIÓN PRIVADA" not in text
    assert "TIPO DE DOCUMENTO" in text and "Proforma - Cotización" in text
    assert text.index("TIPO DE DOCUMENTO") < text.index("Equipamiento Dirección")
    assert "Beatriz Solicitante" in text and "Creador Original" not in text
    assert "<b>Firma autorizada</b>" in text and "<b>Depto. de ventas</b>" in text
    assert "Firma del cliente" in text
    assert "1,2345" in text
    assert "Bs 7.300,00" in text and "Bs 9.900,00" not in text
    assert "Subtotal ítem" not in text and "Descuentos aplicados" not in text
    assert text.index("TOTAL COTIZADO") < text.index("OBSERVACIONES DE LA PROFORMA")
    assert text.index("OBSERVACIONES DE LA PROFORMA") < text.index("CONDICIONES COMERCIALES")


def test_optional_zero_fields_and_negotiated_currency():
    _, text = render(
        quote(
            [line(modo_calculo="TOTAL_NEGOCIADO", importe_negociado=Decimal("7300"), descuento=0)],
            titulo=None,
            observaciones=None,
            porcentaje_adelanto=0,
            plazo_entrega=None,
            validez_oferta=0,
            moneda=NS(codigo="USD"),
        )
    )
    assert "Importe total negociado" in text
    assert "Precio unitario" not in text and "Descuento" not in text
    assert "$us 7.300,00" in text
    assert "OBSERVACIONES DE LA PROFORMA" not in text
    assert "ANTICIPO REQUERIDO" in text and "0 %" in text
    assert "VALIDEZ DE LA OFERTA" in text and "0 días" in text
    assert "PLAZO DE ENTREGA" not in text


def test_technical_hierarchy_preserves_unknown_fields_zero_one_and_relations():
    data = {
        "caracteristicas_generales": {
            "dimensiones": {
                "ancho": {"valor": "1,60", "unidad": "m"},
                "separacion": {"valor": 0, "unidad": "mm"},
                "diametro": {"valor": "33 × 40 × 63"},
            },
            "atributos": [{"nombre": "Especial", "valor": 0}],
            "detalle_extra": "General íntegro",
        },
        "conjuntos": [
            {
                "uid": "c",
                "nombre": "Credenza",
                "dimensiones": "1,50 × 0,65 × 0,45 m",
                "observaciones": "Conjunto íntegro",
            }
        ],
        "componentes": [
            {
                "uid": "p",
                "conjunto_uid": "c",
                "nombre": "Puerta posterior",
                "cantidad_interna": 1,
                "material": {"nombre": "Melamina", "espesor": "18 mm"},
                "detalle": "No abreviar el sistema de cerraduras & montaje.",
                "atributos": [{"nombre": "Paso", "valor": 0}],
            }
        ],
        "advertencias": ["Advertencia completa"],
        "accesorios": ["Chapa frontal", "Chapa frontal"],
        "campo_futuro": {"sistema": "Dato comercial futuro"},
        "descripcion_original": "Descripción fuente completa.",
    }
    _, text = render(quote([line(data)]))
    for value in [
        "DIMENSIONES",
        "ESTRUCTURA",
        "ACCESORIOS",
        "OBSERVACIONES DEL MUEBLE",
        "General íntegro",
        "Conjunto íntegro",
        "Puerta posterior",
        "Cantidad interna",
        "Melamina",
        "18 mm",
        "Advertencia completa",
        "Dato comercial futuro",
        "Descripción fuente completa.",
        "33 × 40 × 63",
    ]:
        assert value in text
    assert text.count("Chapa frontal") == 2
    assert "conjunto_uid" not in text and '"valor"' not in text
    assert text.index("Credenza") < text.index("Puerta posterior")


def test_long_specs_and_observations_paginate_without_layout_error():
    data = {
        "componentes": [
            {
                "nombre": "Cajonera",
                "cantidad_interna": 1,
                "detalle": "Cerraduras con llave: cada cajón conserva su sistema de cierre. " * 500,
            }
        ]
    }
    pdf, text = render(quote([line(data)], observaciones="Observación extensa.\n" * 300))
    assert pdf.count(b"/Type /Page") >= 4
    assert "cada cajón conserva su sistema de cierre" in text


def test_renderer_requires_verified_actor():
    with pytest.raises((TypeError, PermissionError)):
        renderizar_proforma_pdf(1)


@pytest.mark.parametrize("case_index", [0, 1])
def test_approved_complex_cases_preserve_every_commercial_leaf(case_index):
    import html
    import json
    import re
    from pathlib import Path

    cases = json.loads(
        (Path(__file__).parents[2] / "tests/fixtures/proforma_pdf_cases.json").read_text()
    )
    case = cases[case_index]
    _, rendered = render(quote([line(case["datos_tecnicos"], nombre=case["nombre"])]))
    plain = html.unescape(re.sub("<[^>]*>", " ", rendered))

    def leaves(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key not in {"uid", "conjunto_uid"}:
                    yield from leaves(child)
        elif isinstance(value, list):
            for child in value:
                yield from leaves(child)
        elif value is not None:
            yield str(value)

    for leaf in leaves(case["datos_tecnicos"]):
        assert leaf in plain


def test_explicit_anonymous_actor_is_rejected_before_database_access():
    with pytest.raises(PermissionError):
        renderizar_proforma_pdf(1, usuario=NS(is_authenticated=False))


def test_catalogue_attributes_are_not_converted_into_furniture_structure():
    chair = NS(
        marca=NS(nombre="Marca real"),
        modelo="Silla profesional",
        color_primario=None,
        color_secundario=None,
        especificaciones={"carga": 0, "tapizado": "Malla & tela"},
    )
    product = NS(observaciones="Regulación completa", productosilla=chair, productopiso=None)
    _, text = render(
        quote(
            [
                line(
                    especificacionmueble=None,
                    producto_id=20,
                    producto=product,
                    tipo_item=NS(nombre="Silla"),
                )
            ]
        )
    )
    assert "Marca real" in text and "Silla profesional" in text
    assert "Malla &amp; tela" in text and "Regulación completa" in text
    assert "ESTRUCTURA" not in text
    assert "ACCESORIOS Y OBSERVACIONES DEL MUEBLE" not in text


def test_empty_sections_and_whitespace_values_are_absent():
    _, text = render(
        quote(
            [line(especificacionmueble=None, descuento=0)],
            titulo="  ",
            observaciones="  ",
            porcentaje_adelanto=None,
            plazo_entrega="  ",
            validez_oferta=None,
        )
    )
    assert "OBSERVACIONES DE LA PROFORMA" not in text
    assert "CONDICIONES COMERCIALES" not in text
    assert "Descuento" not in text


def test_pdf_text_geometry_full_width_zones_and_header_on_first_page(tmp_path):
    import shutil
    import subprocess
    import xml.etree.ElementTree as ET

    if not shutil.which("pdftotext"):
        pytest.skip("Poppler pdftotext is needed for layout geometry proof")
    data = {
        "componentes": [
            {"nombre": "COMPONENTE", "cantidad_interna": 1, "detalle": "ESPECIFICACION " * 900}
        ]
    }
    pdf, _ = render(quote([line(data)]))
    source, bbox = tmp_path / "layout.pdf", tmp_path / "layout.html"
    source.write_bytes(pdf)
    subprocess.run(["pdftotext", "-bbox", str(source), str(bbox)], check=True)
    ns = {"x": "http://www.w3.org/1999/xhtml"}
    pages = ET.parse(bbox).getroot().findall(".//x:page", ns)
    assert len(pages) >= 3
    words = pages[0].findall(".//x:word", ns)
    assert "ÍTEM" in [word.text for word in words]  # No mostly-blank institutional first page.
    for page in pages:
        words = page.findall(".//x:word", ns)
        assert words
        for word in words:
            assert 38 <= float(word.attrib["xMin"]) < float(word.attrib["xMax"]) <= 574
            assert 35 <= float(word.attrib["yMin"]) < float(word.attrib["yMax"]) <= 775
            if word.text == "ESPECIFICACION":
                assert float(word.attrib["xMin"]) >= 45
    final_words = [word.text for word in pages[-1].findall(".//x:word", ns)]
    assert "Beatriz" in final_words and "Ana" in final_words


def test_issued_status_is_not_labelled_as_draft():
    _, text = render(quote([line()], estado=NS(codigo="EN_REVISION", nombre="En revisión")))
    assert "En revisión" in text
    assert "VISTA PREVIA" not in text


def test_product_card_splits_independent_zones_and_draws_image_once_centered():
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.platypus import Flowable, Table

    from apps.documentos.pdf_layout import Columns, ProductCard

    positions = []

    class RecordingImage(Flowable):
        def __init__(self):
            super().__init__()
            self.width, self.height = 80, 40

        def draw(self):
            positions.append(self.canv._currentMatrix)

    style = getSampleStyleSheet()["Normal"]
    card = ProductCard(
        Table([["Item"]], colWidths=[500]),
        None,
        [
            Columns(
                [[RecordingImage()], [Paragraph("Long specification. " * 150, style)]],
                [150, 350],
                center_first=True,
            )
        ],
        Table([["Subtotal"]], colWidths=[500]),
    )
    parts = card.split(500, 300)
    assert len(parts) == 2
    first, remainder = parts
    assert remainder.image is None
    c = Canvas(BytesIO())
    first.wrap(500, 300)
    first.drawOn(c, 0, 0)
    assert len(positions) == 1
    x, y = positions[0][4:]
    assert x == pytest.approx(first.padding + (150 - 80) / 2)
    assert y == pytest.approx(
        first.padding
        + first.body_height
        - first.content[0].height
        + (first.content[0].height - 40) / 2
    )
    assert not first.final and remainder.final
