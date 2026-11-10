"""Independent-zone and source-integrity regression contracts."""

from copy import deepcopy

import pytest

from apps.documentos.test_pdf_design import line, quote, render


def test_independent_zones_and_operational_metadata():
    data = {
        "caracteristicas_generales": {
            "dimensiones": {f"medida_{i}": {"valor": i, "unidad": "mm"} for i in range(8)},
            "atributos": [{"nombre": "Resistencia futura", "valor": 0, "tipo_entrada": "texto"}],
        },
        "componentes": [{"nombre": "Estructura", "detalle": "Unión reforzada"}],
        "accesorios": ["Pasacables"],
    }
    _, text = render(quote([line(data)], titulo=None))
    assert "DETALLE DE PRODUCTOS" not in text
    assert "Emisión:" in text
    assert "DIMENSIONES" in text and "CARACTERÍSTICAS" in text
    assert "Componente: Estructura" in text
    assert "Tipo entrada" not in text
    assert "OBSERVACIONES DEL MUEBLE" in text
    assert "ACCESORIOS Y OBSERVACIONES" not in text
    assert "<b>Firma del cliente</b>" in text


def test_source_clauses_remove_only_proven_duplicates_without_mutation():
    data = {
        "componentes": [{"nombre": "Puerta", "detalle": "La puerta tiene cerradura propia."}],
        "descripcion_original": (
            "La puerta tiene cerradura propia. El cajón tiene cerradura propia."
        ),
    }
    before = deepcopy(data)
    _, text = render(quote([line(data, descripcion=None)]))
    assert "Descripción original" not in text
    assert text.count("La puerta tiene cerradura propia.") == 1
    assert "El cajón tiene cerradura propia." in text
    assert "Información técnica adicional" not in text
    assert text.index("El cajón tiene cerradura propia.") > text.index("OBSERVACIONES DEL MUEBLE")
    assert data == before


def test_fully_duplicated_source_has_no_additional_block():
    data = {
        "observaciones": "Montar con anclaje reforzado.",
        "descripcion_original": "Montar con anclaje reforzado.",
    }
    _, text = render(quote([line(data, descripcion=None)]))
    assert text.count("Montar con anclaje reforzado.") == 1
    assert "Información técnica adicional" not in text


@pytest.mark.parametrize("count", [1, 2, 3, 7])
def test_variable_dimensions_sets_and_associated_accessories(count):
    data = {
        "caracteristicas_generales": {
            "dimensiones": {
                f"medida_{i}": {"valor": i, "unidad": "unidad extensa de fabricación"}
                for i in range(count)
            }
        },
        "conjuntos": [{"uid": f"g{i}", "nombre": f"Grupo {i}"} for i in range(count)],
        "componentes": [
            {"uid": "c0", "conjunto_uid": "g0", "nombre": "Puerta", "cantidad_interna": 1}
        ],
        "accesorios": [{"componente_uid": "c0", "nombre": "Cerradura", "cantidad": 0}],
    }
    _, text = render(quote([line(data)]))
    for i in range(count):
        assert f"Grupo {i}" in text
        assert f"Medida {i}" in text
    assert "Puerta" in text and "Cerradura" in text
    assert "componente_uid" not in text


def test_description_source_is_not_repeated_as_raw_dictation():
    data = {
        "observaciones": "Fijar a pared.",
        "descripcion_original": "Fijar a pared. Conservar acceso posterior.",
    }
    _, text = render(quote([line(data, descripcion=data["descripcion_original"])]))
    assert text.count("Fijar a pared.") == 1
    assert text.count("Conservar acceso posterior.") == 1


@pytest.mark.parametrize("with_image", [True, False])
def test_image_and_independent_zone_geometry(tmp_path, with_image):
    import subprocess
    import xml.etree.ElementTree as ET
    from io import BytesIO

    from PIL import Image
    from reportlab.platypus import Image as PdfImage

    image = BytesIO()
    Image.new("RGB", (450, 180), "#d6b28b").save(image, "PNG")

    def photo(_):
        return PdfImage(BytesIO(image.getvalue()), width=120, height=48)

    data = {
        "caracteristicas_generales": {
            "material": "GENERALMARK",
            "dimensiones": {"ancho": {"valor": 0, "unidad": "cm"}},
        },
        "componentes": [
            {"nombre": "STRUCTUREMARK", "detalle": "Componente con especificaciones completas"}
        ],
    }
    pdf, text = render(
        quote(
            [
                line(
                    data,
                    nombre=(
                        "Nombre largo de producto que necesita varias líneas "
                        "y debe permanecer separado de su categoría "
                    )
                    * 3,
                )
            ]
        ),
        image_factory=photo if with_image else None,
    )
    assert "Sin imagen" not in text
    path = tmp_path / "image.pdf"
    path.write_bytes(pdf)
    bbox = tmp_path / "image.html"
    subprocess.run(["pdftotext", "-bbox", str(path), str(bbox)], check=True)
    ns = {"x": "http://www.w3.org/1999/xhtml"}
    words = ET.parse(bbox).getroot().findall(".//x:word", ns)
    general = next(word for word in words if word.text == "GENERALMARK")
    structure = next(word for word in words if word.text == "STRUCTUREMARK")
    if with_image:
        assert float(general.attrib["xMin"]) > 185
    else:
        assert float(general.attrib["xMin"]) < 150
    assert float(structure.attrib["xMin"]) < 150
    assert float(structure.attrib["yMin"]) > float(general.attrib["yMax"])
    subtotals = [word for word in words if word.text == "7.300,00"]
    assert any(float(word.attrib["xMax"]) == pytest.approx(558.315, abs=1) for word in subtotals)


def test_many_sets_long_cells_and_observation_paragraphs_paginate(tmp_path):
    import subprocess
    import xml.etree.ElementTree as ET

    data = {
        "conjuntos": [
            {
                "uid": str(i),
                "nombre": f"Conjunto {i}",
                "dimensiones": {"profundidad": {"valor": 0, "unidad": "mm"}},
            }
            for i in range(5)
        ],
        "componentes": [
            {"conjunto_uid": "0", "nombre": "Estructura", "detalle": "RELATIONDETAIL " * 1200}
        ],
        "observaciones": "Primer párrafo íntegro.\n\nSegundo párrafo íntegro. " * 80,
    }
    pdf, text = render(quote([line(data)]))
    assert "Segundo párrafo íntegro" in text
    path = tmp_path / "long.pdf"
    path.write_bytes(pdf)
    bbox = tmp_path / "long.html"
    subprocess.run(["pdftotext", "-bbox", str(path), str(bbox)], check=True)
    ns = {"x": "http://www.w3.org/1999/xhtml"}
    pages = ET.parse(bbox).getroot().findall(".//x:page", ns)
    assert len(pages) >= 3
    for page in pages:
        words = page.findall(".//x:word", ns)
        assert len(words) > 10
        for word in words:
            assert 38 <= float(word.attrib["xMin"]) < float(word.attrib["xMax"]) <= 574
            assert 35 <= float(word.attrib["yMin"]) < float(word.attrib["yMax"]) <= 775


def test_unstructured_component_context_keeps_its_identical_lock_clause():
    source = "Credenza posterior. Cerradura con llave independiente."
    data = {
        "componentes": [
            {"nombre": "Cajones principales", "cerradura": "Cerradura con llave independiente."}
        ],
        "descripcion_original": source,
    }
    before = deepcopy(data)
    _, text = render(quote([line(data, descripcion=None)]))
    assert "Credenza posterior.<br/>Cerradura con llave independiente." in text
    assert text.index("Credenza posterior.") > text.index("OBSERVACIONES DEL MUEBLE")
    assert data == before


def test_fully_duplicated_natural_descriptive_source_is_hidden():
    data = {
        "componentes": [
            {"nombre": "Puerta", "detalle": "La puerta tiene cerradura propia."},
            {"nombre": "Cajón", "detalle": "El cajón tiene guía telescópica."},
        ],
        "descripcion_original": (
            "La puerta tiene cerradura propia. El cajón tiene guía telescópica."
        ),
    }
    _, text = render(quote([line(data, descripcion=None)]))
    assert "Información técnica adicional" not in text
    assert text.count("La puerta tiene cerradura propia.") == 1
    assert text.count("El cajón tiene guía telescópica.") == 1


def test_identical_description_and_source_preserve_measurements_material_and_amount_once():
    source = "Ancho 160 cm, alto 73 cm y profundidad 60 cm. Material MDP de 25 mm. Importe Bs 7300."
    data = {
        "caracteristicas_generales": {
            "dimensiones": {"ancho": {"valor": 160, "unidad": "cm"}},
            "material": "MDP de 25 mm",
        },
        "descripcion_original": source,
    }
    _, text = render(quote([line(data, descripcion=source)]))
    assert text.count("Ancho 160 cm, alto 73 cm y profundidad 60 cm.") == 1
    assert text.count("Material MDP de 25 mm.") == 1
    assert text.count("Importe Bs 7300.") == 1


def test_different_source_contexts_do_not_merge_identical_lock_clauses():
    data = {
        "componentes": [
            {"nombre": "Cajones principales", "cerradura": "Cerradura con llave independiente."}
        ],
        "descripcion_original": "Credenza posterior. Cerradura con llave independiente.",
    }
    _, text = render(
        quote([line(data, descripcion="Puerta lateral. Cerradura con llave independiente.")])
    )
    assert "Puerta lateral.<br/>Cerradura con llave independiente." in text
    assert "Credenza posterior.<br/>Cerradura con llave independiente." in text


def test_technical_red_does_not_restyle_approved_commercial_closing():
    from unittest.mock import patch

    from reportlab.lib.colors import HexColor
    from reportlab.platypus import Paragraph

    styles = {}

    def record(value, style, *args, **kwargs):
        styles[value] = style.textColor
        return Paragraph(value, style, *args, **kwargs)

    with patch("apps.documentos.test_pdf_design.Paragraph", side_effect=record):
        render(quote([line({"caracteristicas_generales": {"material": "Melamina"}})]))
    assert styles["CARACTERÍSTICAS"] == HexColor("#b91c1c")
    assert styles["OBSERVACIONES DE LA PROFORMA"] == HexColor("#0f172a")
    assert styles["CONDICIONES COMERCIALES"] == HexColor("#0f172a")
