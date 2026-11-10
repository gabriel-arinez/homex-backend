"""Sketch-specific visual primitives and conservative capture coverage."""

from copy import deepcopy
from io import BytesIO

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

from apps.documentos.pdf_layout import ProductCard
from apps.documentos.pdf_source import additional_source
from apps.documentos.test_pdf_design import line, quote, render

MEETING_SOURCE = (
    "Mesa de reunión para 12 personas, de 3 metros de largo, "
    "1.25 metros de ancho y 0.78 metros de alto.\n"
    "Estructura de melamina de 18 milímetros, mesón de 27 milímetros, "
    "2 tomacorrientes al centro, precio unitario, 8.050 bolivianos, secotiza una sola mesa."
)
MEETING = {
    "caracteristicas_generales": {
        "dimensiones": {
            "alto": {"valor": "0.78", "unidad": "m"},
            "ancho": {"valor": "1.25", "unidad": "m"},
            "largo": {"valor": "3", "unidad": "m"},
        }
    },
    "componentes": [
        {"nombre": "Estructura", "material": "melamina", "espesor": "18 mm"},
        {"nombre": "mesón", "espesor": "27 mm"},
    ],
    "accesorios": ["2 tomacorrientes al centro"],
    "descripcion_original": MEETING_SOURCE,
}
SHELF_SOURCE = (
    "Necesito un estante de pared, una unidad de 1 metro de ancho por "
    "0.20 metros de profundidad y 1.80 metros de alto.\n"
    "Fabricado en melamina de 18 milímetros, color blanco con cuatro repisas abiertas "
    "y sin puertas.\nPrecio unitario 1350 bolivianos."
)
SHELF = {
    "caracteristicas_generales": {
        "material": "melamina",
        "color": "blanco",
        "dimensiones": {
            "alto": {"valor": "1.80", "unidad": "m"},
            "ancho": {"valor": "1", "unidad": "m"},
            "profundidad": {"valor": "0.20", "unidad": "m"},
        },
    },
    "componentes": [{"nombre": "repisas abiertas", "cantidad_interna": 4}],
    "observaciones": "sin puertas",
    "descripcion_original": SHELF_SOURCE,
}


def test_real_meeting_capture_is_covered_without_obsolete_commercial_narration():
    before = deepcopy(MEETING)
    _, text = render(
        quote(
            [
                line(
                    MEETING,
                    nombre="Mesa de reunión para 12 personas",
                    descripcion=None,
                    cantidad=3,
                    precio_unitario=8050,
                    total=24150,
                    descuento=0,
                )
            ],
            total=24150,
        )
    )
    assert "Información técnica adicional" not in text
    assert "secotiza" not in text and "metros de largo" not in text
    assert "Bs 24.150,00" in text and "3 Pieza" in text
    assert MEETING == before


def test_shelf_missing_thickness_stays_verbatim_in_existing_observations():
    _, text = render(
        quote(
            [
                line(
                    SHELF,
                    nombre="estante de pared",
                    descripcion=None,
                    cantidad=1,
                    precio_unitario=1350,
                    total=1350,
                    descuento=0,
                )
            ],
            total=1350,
        )
    )
    assert "Información técnica adicional" not in text
    assert "Necesito un estante" not in text
    assert "Precio unitario 1350 bolivianos" not in text
    assert "sin puertas" in text


def test_rounded_outer_and_nested_panels_draw_and_split():
    from apps.documentos.pdf_layout import RoundedPanel

    style = getSampleStyleSheet()["Normal"]
    panel = RoundedPanel([Paragraph("Long readable technical content. " * 600, style)])
    parts = panel.split(240, 250)
    assert len(parts) == 2
    assert all(isinstance(part, RoundedPanel) for part in parts)
    c = Canvas(BytesIO())
    calls = []
    original = c.roundRect

    def record(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    c.roundRect = record
    card = ProductCard(
        Paragraph("Item header", style),
        None,
        [RoundedPanel([Paragraph("Fact", style)])],
        Paragraph("Subtotal", style),
    )
    card.wrap(500, 700)
    card.drawOn(c, 0, 0)
    assert len(calls) >= 2
    assert calls[0][0][2] == 500
    assert calls[1][0][2] < 500


def test_source_unknown_context_and_missing_units_never_prove_coverage():
    data = {
        "componentes": [{"nombre": "Cajones", "cerradura": "Cerradura propia."}],
        "caracteristicas_generales": {"dimensiones": {"alto": {"valor": 18}}},
    }
    assert additional_source("Puerta. Cerradura propia.", data) == ["Puerta.", "Cerradura propia."]
    assert additional_source("Alto 18 mm.", data) == ["Alto 18 mm."]


def test_capture_thickness_requires_same_named_component_and_explicit_unit():
    data = deepcopy(MEETING)
    data["componentes"][0]["espesor"] = "27 mm"
    data["componentes"][1]["espesor"] = "18 mm"
    source = "Estructura de melamina de 18 milímetros, mesón de 27 milímetros."
    assert additional_source(source, data) == [source]
    data["componentes"][0]["espesor"] = {"valor": 18}
    assert additional_source(source, data) == [source]
    data["componentes"][0]["espesor"] = {"valor": 18, "unidad": "mm"}
    data["componentes"][1]["espesor"] = "27 mm"
    assert additional_source(source, data) == []


def test_grid_shapes_uniform_gutters_and_long_values(monkeypatch):
    import apps.documentos.pdf as renderer
    from apps.documentos.pdf_layout import RoundedPanel

    columns = []
    original = renderer.Columns

    def record(*args, **kwargs):
        grid = original(*args, **kwargs)
        columns.append(grid)
        return grid

    monkeypatch.setattr(renderer, "Columns", record)
    data = {
        "caracteristicas_generales": {
            "dimensiones": {
                f"Etiqueta larga {i}": {"valor": i, "unidad": "unidad extensa " * 6}
                for i in range(7)
            },
            "atributos": [
                {"nombre": f"Atributo {i}", "valor": "Valor completo " * 5} for i in range(5)
            ],
        }
    }
    _, text = render(quote([line(data, descripcion=None)]))
    grids = [
        grid
        for grid in columns
        if any(items and isinstance(items[0], RoundedPanel) for items in grid.columns)
    ]
    assert [len(grid.columns) for grid in grids] == [3, 3, 3, 2, 2, 2]
    for grid in grids:
        grid.wrap(490, 700)
        for items, width in zip(grid.columns, grid.column_widths, strict=True):
            if items:
                assert items[0].width == width - 10
                assert items[0].height > 20
    for i in range(7):
        assert f"Etiqueta larga {i}" in text
    assert "3 COLUMNAS" not in text and "2 COLUMNAS" not in text


def test_heading_cannot_be_taken_without_start_of_rounded_panel():
    from reportlab.lib.styles import ParagraphStyle

    from apps.documentos.pdf_layout import RoundedPanel, take

    style = getSampleStyleSheet()["Normal"]
    heading = Paragraph("ESTRUCTURA", ParagraphStyle("Heading", parent=style, keepWithNext=True))
    panel = RoundedPanel([Paragraph("Long specification. " * 300, style)])
    head, tail = take([heading, panel], 240, 50)
    assert head == [] and tail == [heading, panel]


def test_long_rounded_panels_preserve_every_rendered_token_and_final_economics(tmp_path):
    import subprocess

    data = {
        "componentes": [
            {"nombre": "Panel extenso", "detalle": "TOKENINTEGRO " * 2000 + "FINCOMPONENTE"}
        ],
        "observaciones": "NOTAINTEGRA " * 1100 + "FINOBSERVACION",
    }
    pdf, _ = render(quote([line(data, descripcion=None, descuento=0)], total=7300))
    source = tmp_path / "rounded-long.pdf"
    source.write_bytes(pdf)
    text = subprocess.check_output(["pdftotext", str(source), "-"], text=True)
    assert text.count("TOKENINTEGRO") == 2000
    assert text.count("NOTAINTEGRA") == 1100
    assert text.count("FINCOMPONENTE") == 1
    assert text.count("FINOBSERVACION") == 1
    assert text.index("SUBTOTAL") > text.index("FINOBSERVACION")
    assert text.count("Beatriz Solicitante") == 1
