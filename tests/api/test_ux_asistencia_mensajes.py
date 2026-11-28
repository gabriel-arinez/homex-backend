"""Regression tests for natural-Spanish pending messages and ROL_MATERIAL filtering."""

import pytest
from rest_framework.test import APIClient

from tests.api.test_final_inferred_projection import review
from tests.factories import vendedor

pytestmark = pytest.mark.django_db(transaction=True)

REPRO_TRANSCRIPT = (
    "Necesito una mesa de reunión para 10 personas. Una pieza de 2.40 metros de largo, "
    "1.20 metros de ancho y 0.80 metros de alto. Tablero de melamina de 18 milímetros "
    "con mesón engrosado a 27 milímetros. Tapacanto de PVC y 2 tomacorrientes al centro. "
    "Precio unitario 7.280 bolivianos"
)


@pytest.fixture(name="intake")
def ux_api(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ux-asistencia-review"))
    api = APIClient()
    api.force_authenticate(actor)
    return api


def test_mesa_reunion_explicit_melamina_emits_no_rol_material_pending(intake):
    result = review(intake, REPRO_TRANSCRIPT)
    proposal = result["propuesta_configurador"]
    assert proposal is not None
    assert proposal["pendientes"] == []
    assert any(c["label"] == "ROL_MATERIAL" for c in result["candidatos"])
    componentes = {
        c["nombre"].lower(): c for c in proposal["especificacion"]["datos_tecnicos"]["componentes"]
    }
    assert componentes["tablero"]["material"] == "melamina"
    assert componentes["tablero"]["espesor"] == "18 mm"
    assert componentes["mesón"]["espesor"] == "27 mm"
    assert proposal["comercial"]["precio_unitario"] == "7280.00"


@pytest.mark.parametrize(
    "material_phrase",
    ["melamina", "MDF", "MDP", "vidrio templado", "PVC", "acero cromado"],
)
def test_explicit_materials_never_expose_rol_material_or_json(intake, material_phrase):
    result = review(intake, f"Un escritorio de {material_phrase} de 120 cm de ancho.")
    proposal = result["propuesta_configurador"]
    assert not any(p["codigo"] == "ROL_MATERIAL" for p in proposal["pendientes"])
    for pending in proposal["pendientes"]:
        msg = pending["mensaje"]
        assert "{" not in msg and "}" not in msg
        assert "coating_or_board_description" not in msg
        assert "UNRESOLVED" not in msg
        assert "component_ref" not in msg


def test_all_review_pending_types_use_natural_spanish_and_actionable_routes(intake):
    cases = [
        (
            "un estante con tablero de me lamina marca nobopan, garantía de dos años",
            "RECUPERACION_LEXICA",
        ),
        ("Una mesa de madera enchapada.", "ESPECIFICACION"),
        ("Un escritorio en L de 160 por 80", "GEOMETRIA"),
        ("una mesa con altura regulable de 70 a 90 cm", "RANGO_DIMENSIONAL"),
        ("Un escritorio con tres cajones por lado.", "DISTRIBUCION"),
        ("Una mesa simple. Color a elección.", "SELECCION_COLOR"),
        ("Un escritorio de melamina. Color maderable con negro.", "COLOR_NO_RESUELTO"),
    ]
    for text, expected_code in cases:
        proposal = review(intake, text)["propuesta_configurador"]
        matches = [p for p in proposal["pendientes"] if p["codigo"] == expected_code]
        assert matches, f"Expected {expected_code} for {text!r}, got {proposal['pendientes']}"
        for p in proposal["pendientes"]:
            msg = p["mensaje"]
            assert "{" not in msg and "}" not in msg and "→" not in msg
            assert "Confirm " not in msg and "requires review" not in msg
        if expected_code == "DISTRIBUCION":
            assert matches[0]["resolucion"]["tipo"] == "COMPONENTE"
            assert matches[0]["resolucion"]["campo"] == "cantidad_interna"
        elif expected_code in {"SELECCION_COLOR", "COLOR_NO_RESUELTO"}:
            assert matches[0]["resolucion"] == {"tipo": "ATRIBUTO_GENERAL", "clave": "color"}
        elif expected_code in {"ESPECIFICACION", "RANGO_DIMENSIONAL", "GEOMETRIA"}:
            assert matches[0]["resolucion"] == {"tipo": "OBSERVACIONES"}
