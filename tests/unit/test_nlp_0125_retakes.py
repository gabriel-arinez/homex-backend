"""Real installed NLP adapter preserves literal retake fields under schema v1."""

import pytest

from apps.capturas.nlp import AdaptadorNLP


@pytest.fixture(autouse=True)
def catalogo_estructural():
    yield


@pytest.fixture(autouse=True)
def transiciones_pedido():
    yield


@pytest.mark.parametrize("quantity, height", [(2, 73), (3, 63), (6, 63)])
def test_installed_adapter_keeps_recognized_quantity_price_and_component_chain(quantity, height):
    result = AdaptadorNLP().extraer(
        solicitud_id="retake-consumer",
        texto=(
            f"{quantity} escritorios con cajonera, escritorio de 1,40 m x 70 cm "
            f"con una altura de 73 cm, cajonera de 33 x 40 x {height} cm. "
            "Precio unitario 1600 bolivianos."
        ),
        moneda="BOB",
    )
    assert result.estado == "REQUIRES_REVIEW"
    assert result.version_contrato == "1.0" and result.motor["mode"] == "RULES_ONLY"
    item = result.propuesta
    assert item.cantidad == quantity
    assert item.precio["line_total"] == f"{quantity * 1600}.00"
    drawer = next(c["component_id"] for c in item.componentes if c["name"] == "cajonera")
    assert [(d["axis"], d["value_mm"]) for d in item.dimensiones if d["axis"]] == [("alto", "730")]
    assert [d["value_mm"] for d in item.dimensiones if d["component_ref"] == drawer] == [
        "330",
        "400",
        str(height * 10),
    ]
    assert all(d["axis"] is None for d in item.dimensiones if d["component_ref"] == drawer)
    assert list(item.dimensiones) == result.resultado_original["item_proposal"]["dimensions"]
    assert list(item.componentes) == result.resultado_original["item_proposal"]["components"]
    assert list(result.candidatos) == result.resultado_original["candidates"]


@pytest.mark.parametrize(
    "description, measurement_count, pending_counts",
    [("de 33 x 40 x 63 cm", 3, [1, 1, 1]), (". Embalaje 33 x 40 cm", 0, [2])],
)
def test_projection_preserves_unknown_axes_without_duplicate_chain_requests(
    monkeypatch, description, measurement_count, pending_counts
):
    from types import SimpleNamespace

    from apps.capturas import proyeccion_prf03 as projection

    # Catalog lookup is irrelevant to this unit: preserve the unresolved type.
    monkeypatch.setattr(
        projection.MetadatoAtributoMueble.objects,
        "select_related",
        lambda *args: SimpleNamespace(filter=lambda **kwargs: []),
    )
    monkeypatch.setattr(projection.ValorCatalogo.objects, "filter", lambda **kwargs: [])
    result = AdaptadorNLP().extraer(
        solicitud_id="chain-projection",
        texto=f"Una mesa {description}. Precio unitario 900 bolivianos.",
        moneda="BOB",
    )
    assert len(result.propuesta.dimensiones) == measurement_count
    projected = projection.proyectar(result.resultado_original)
    missing_axes = [p for p in projected["pendientes"] if p["codigo"] == "MISSING_AXIS"]
    assert len(missing_axes) == len(pending_counts)
    assert [p["resolucion"] for p in missing_axes] == [
        {"tipo": "DIMENSIONES_NUEVAS", "cantidad": n} for n in pending_counts
    ]
    assert projected["comercial"]["cantidad"] == 1
    assert projected["comercial"]["precio_unitario"] == "900.00"
    assert projected["especificacion"]["datos_tecnicos"].get("dimensiones", {}) == {}
