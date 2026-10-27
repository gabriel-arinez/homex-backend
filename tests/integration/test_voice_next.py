"""Replays textuales y controles de proyección, en PostgreSQL aislado."""

import pytest

from apps.capturas.nlp import AdaptadorNLP
from apps.capturas.proyeccion_prf03 import proyectar
from apps.catalogo.models import ValorCatalogo

pytestmark = pytest.mark.django_db


def projection(text):
    result = AdaptadorNLP().extraer(solicitud_id="voice-next", texto=text, moneda="BOB")
    return proyectar(result.resultado_original)


def test_ambiguous_price_is_never_autocompleted():
    result = projection("Una mesa presionitario 8.50 bolivianos")
    assert result["comercial"]["precio_unitario"] is None
    assert any(p["codigo"] == "INVALID_PRICE" for p in result["pendientes"])


def test_repeated_material_is_not_conflict():
    result = projection("Un estante de melamine, melamina de 18 mm")
    assert not any(p["codigo"] == "CONFLICTING_VALUES" for p in result["pendientes"])


def test_real_material_conflict_requires_review():
    result = projection("Un estante de melamina, MDF")
    assert any(p["codigo"] == "CONFLICTING_VALUES" for p in result["pendientes"])


def test_color_does_not_become_door_material():
    result = projection(
        "Un atril de melamina con una puerta y una repisa interior color madera clara"
    )
    components = result["especificacion"]["datos_tecnicos"]["componentes"]
    assert [p["nombre"] for p in components] == ["puerta", "repisa"]
    assert all("material" not in p for p in components)


@pytest.mark.parametrize(
    ("term", "code"),
    [
        ("escritorios en L", "ESCRITORIO"),
        ("mesas de reunión para 6 personas", "MESA_REUNION"),
        ("gabeteros", "GAVETERO"),
        ("credenzas", "CREDENZA"),
    ],
)
def test_types_use_real_active_catalog_ids(term, code):
    result = projection(f"Dos {term}")
    expected = ValorCatalogo.objects.get(concepto__codigo="TIPO_MUEBLE", codigo=code)
    assert result["especificacion"]["tipo_mueble"] == expected.pk


@pytest.mark.parametrize("term", ["veladores", "atril", "mueble de recepción"])
def test_unknown_type_remains_pending(term):
    result = projection(f"Un {term}")
    assert result["especificacion"]["tipo_mueble"] is None
    assert any(p["codigo"] == "TIPO_NO_RESUELTO" for p in result["pendientes"])


def test_nogal_normalized_color_is_projected():
    result = projection("Una credenza color no-gal")
    attrs = result["especificacion"]["datos_tecnicos"]["caracteristicas_generales"]["atributos"]
    assert next(a["valor"] for a in attrs if a["nombre"].lower() == "color") == "nogal"
