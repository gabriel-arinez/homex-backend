"""Review suggestions survive the public pipeline without becoming spoken facts."""

import pytest
from rest_framework.test import APIClient

from apps.capturas.models import IntentoCaptura
from apps.capturas.pipeline import procesar_intento
from tests.api.test_final_partial_capture import entry
from tests.factories import vendedor

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(name="intake")
def partial_api(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="inferred-review"))
    api = APIClient()
    api.force_authenticate(actor)
    return api


def review(api, text):
    received = api.post("/api/v1/capturas/asistidas/", entry(text), format="json")
    assert received.status_code == 202, received.data
    assert procesar_intento(intento_id=received.data["intento_id"]) == "FINALIZADO"
    response = api.get(f"/api/v1/capturas/asistidas/{received.data['id']}/")
    assert response.status_code == 200, response.data
    raw = IntentoCaptura.objects.get(pk=received.data["intento_id"]).resultado_raw
    assert response.data["candidatos"] == raw["candidates"]
    for candidate in response.data["candidatos"]:
        assert text[candidate["start"] : candidate["end"]] == candidate["text"]
    return response.data


def test_inferred_axes_remain_blank_and_explicit_measure_is_retained(intake):
    result = review(
        intake, "un escritorio de 90 centímetros de ancho, 43 de profundidad y 70 de alto"
    )
    proposal = result["propuesta_configurador"]
    dimensions = proposal["especificacion"]["datos_tecnicos"]["caracteristicas_generales"][
        "dimensiones"
    ]
    assert dimensions == {"ancho": {"valor": "90", "unidad": "cm"}}
    for axis, value in [("alto", "70"), ("profundidad", "43")]:
        pending = next(
            p
            for p in proposal["pendientes"]
            if p.get("resolucion") == {"tipo": "DIMENSION", "clave": axis}
        )
        assert value in pending["mensaje"] and "cm" in pending["mensaje"]
        assert "inferida" in pending["mensaje"].lower()


def test_inferred_chain_suggests_values_without_inventing_axes(intake):
    proposal = review(intake, "una mesa de dos por tres")["propuesta_configurador"]
    assert not proposal["especificacion"]["datos_tecnicos"]["caracteristicas_generales"].get(
        "dimensiones"
    )
    pending = next(
        p
        for p in proposal["pendientes"]
        if p.get("resolucion") == {"tipo": "DIMENSIONES_NUEVAS", "cantidad": 2}
    )
    assert "2 m" in pending["mensaje"] and "3 m" in pending["mensaje"]
    assert "inferida" in pending["mensaje"].lower()


def test_shared_gauge_is_not_automatically_applied_as_explicit(intake):
    proposal = review(intake, "un escritorio con tablero de 18 y 36 mm")["propuesta_configurador"]
    board = proposal["especificacion"]["datos_tecnicos"]["componentes"][0]
    assert board["espesor"] == "36 mm"
    pending = next(
        p
        for p in proposal["pendientes"]
        if p.get("resolucion") == {"tipo": "ESPESOR_SIN_COMPONENTE", "valor": "18 mm"}
    )
    assert pending["codigo"] == "ESPESOR_SIN_COMPONENTE"
    assert "18 mm" in pending["mensaje"] and "compartida" in pending["mensaje"].lower()


@pytest.mark.parametrize(
    "text,amount,equivalent",
    [
        ("un escritorio precio de 13 mil 200 bolivianos", "13200", True),
        ("dos escritorios precio de mil cien bolivianos", "1100", False),
    ],
)
def test_ambiguous_complete_amount_stays_reviewable_not_explicit(intake, text, amount, equivalent):
    result = review(intake, text)
    proposal = result["propuesta_configurador"]
    assert proposal["comercial"]["precio_unitario"] is None
    pending = next(p for p in proposal["pendientes"] if p["codigo"] == "PRECIO_AMBIGUO")
    assert amount in pending["mensaje"]
    assert ("equivalencia" in pending["mensaje"].lower()) is equivalent
    assert "modalidad" in pending["mensaje"].lower()
    assert not any(p["codigo"] == "TOTAL_NEGOCIADO" for p in proposal["pendientes"])


def test_knowledge_recovery_is_visible_without_claiming_material_role(intake):
    result = review(
        intake, "un estante con tablero de me lamina marca nobopan, garantía de dos años"
    )
    proposal = result["propuesta_configurador"]
    assert proposal is not None, result
    messages = "; ".join(p["mensaje"] for p in proposal["pendientes"])
    assert "melamina" in messages.lower() and "nobopan" in messages.lower()
    assert any(p["codigo"] == "RECUPERACION_LEXICA" for p in proposal["pendientes"])
    assert any(p["codigo"] == "ROL_MATERIAL" for p in proposal["pendientes"])
    attributes = proposal["especificacion"]["datos_tecnicos"]["caracteristicas_generales"][
        "atributos"
    ]
    assert any(a["nombre"] == "Marca" and a["valor"] == "Novopan" for a in attributes)
    assert "garantía de dos años" in proposal["especificacion"]["observaciones"]
    assert not any(a["nombre"].lower() in {"sustrato", "recubrimiento"} for a in attributes)


def test_accessory_material_and_geometry_are_not_general_material_or_axes(intake):
    proposal = review(
        intake, "una mesa con jaladores de acero cromado, altura regulable de 70 a 90 cm"
    )["propuesta_configurador"]
    general = proposal["especificacion"]["datos_tecnicos"]["caracteristicas_generales"]
    assert not general.get("dimensiones")
    assert not any(a["nombre"].lower() == "material" for a in general.get("atributos", []))
    assert "acero cromado" in "; ".join(proposal["especificacion"]["datos_tecnicos"]["accesorios"])
    assert any(p["codigo"] == "RANGO_DIMENSIONAL" for p in proposal["pendientes"])


def test_component_aggregate_does_not_auto_resolve_inferred_measurements(intake):
    result = review(
        intake,
        "un escritorio con credenza de 90 centímetros de ancho, 43 de profundidad y 70 de alto",
    )
    proposal = result["propuesta_configurador"]
    piece = proposal["especificacion"]["datos_tecnicos"]["componentes"][0]
    assert piece["dimensiones"] == "ancho: 90 cm"
    pending = [
        p
        for p in proposal["pendientes"]
        if p.get("resolucion")
        == {
            "tipo": "COMPONENTE",
            "uid": piece["uid"],
            "campo": "dimensiones",
            "valor": p.get("resolucion", {}).get("valor"),
        }
        and p["resolucion"].get("valor") in {"alto", "profundidad"}
    ]
    assert pending
    messages = "; ".join(p["mensaje"] for p in pending)
    assert "43 cm" in messages and "70 cm" in messages


def test_explicit_color_combination_is_not_a_conflict(intake):
    proposal = review(intake, "Un escritorio de melamina. Color wengué con negro.")[
        "propuesta_configurador"
    ]
    general = proposal["especificacion"]["datos_tecnicos"]["caracteristicas_generales"]
    assert general["color_principal"] == "wengué"
    assert general["color_secundario"] == "negro"
    assert any(
        a["nombre"] == "Color principal" and a["valor"] == "wengué" for a in general["atributos"]
    )
    assert any(
        a["nombre"] == "Color secundario" and a["valor"] == "negro" for a in general["atributos"]
    )
    assert not any(
        p["codigo"] == "CONFLICTING_VALUES" and p["ruta"].endswith(".color")
        for p in proposal["pendientes"]
    )


@pytest.mark.parametrize(
    "text,code",
    [
        ("Una mesa simple. Color a elección.", "SELECCION_COLOR"),
        ("Un escritorio de melamina. Color maderable con negro.", "COLOR_NO_RESUELTO"),
        ("Un escritorio con tres cajones por lado.", "DISTRIBUCION"),
    ],
)
def test_new_pending_knowledge_does_not_become_explicit_fields(intake, text, code):
    proposal = review(intake, text)["propuesta_configurador"]
    assert any(p["codigo"] == code for p in proposal["pendientes"])
    general = proposal["especificacion"]["datos_tecnicos"]["caracteristicas_generales"]
    assert not general.get("color_principal")
    assert not general.get("color_secundario")
    if code == "DISTRIBUCION":
        assert not any(
            "cantidad_interna" in p
            for p in proposal["especificacion"]["datos_tecnicos"]["componentes"]
        )


@pytest.mark.parametrize(
    "value,accepted",
    [
        ("ancho: 90 cm", False),
        ("ancho: 90 cm; profundidad: 0 cm", False),
        ("ancho: 90 cm; profundidad: 62 kg", False),
        ("ancho: 90 cm; profundidad: 62 cm", True),
    ],
)
def test_saved_component_review_requires_the_pending_axis_not_other_axes(intake, value, accepted):
    from uuid import uuid4

    from apps.proformas.models import Proforma
    from tests.api.test_ap3_proformas_integrales import payload_integral

    data = entry("un escritorio con credenza de 90 centímetros de ancho, 43 de profundidad")
    received = intake.post("/api/v1/capturas/asistidas/", data, format="json")
    assert received.status_code == 202, received.data
    assert procesar_intento(intento_id=received.data["intento_id"]) == "FINALIZADO"
    proposal = intake.get(f"/api/v1/capturas/asistidas/{received.data['id']}/").data[
        "propuesta_configurador"
    ]
    original = proposal["especificacion"]["datos_tecnicos"]["componentes"][0]
    index = next(
        i
        for i, p in enumerate(proposal["pendientes"])
        if p.get("resolucion", {}).get("valor") == "profundidad"
    )
    payload = payload_integral(clave=uuid4())
    payload["sesion_borrador"] = data["sesion_borrador"]
    line = payload["detalles"][0]
    line["captura_asistida_id"] = received.data["id"]
    line["especificacion"]["datos_tecnicos"] = {
        "componentes": [original | {"dimensiones": value}],
        "revision_humana_voz": [
            {
                "captura_asistida_id": received.data["id"],
                "pendientes_originales": proposal["pendientes"],
                "decisiones": [
                    {
                        "decision_id": str(uuid4()),
                        "review_id": f"pending:{index}",
                        "field": f"componentes.{original['uid']}.dimensiones",
                        "evidence_ids": [],
                        "estado": "corregido",
                        "valor_original": original["dimensiones"],
                        "valor_final": value,
                    }
                ],
            }
        ],
    }
    response = intake.post("/api/v1/proformas/integral/", payload, format="json")
    assert response.status_code == (201 if accepted else 400), response.data
    assert Proforma.objects.exists() is accepted
