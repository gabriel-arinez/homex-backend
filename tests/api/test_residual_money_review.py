"""Quantity-one monetary suggestions use the existing trusted human review."""

from uuid import uuid4

import pytest

from apps.capturas.models import IntentoCaptura
from apps.capturas.pipeline import procesar_intento
from apps.proformas.models import EspecificacionMueble, Proforma
from tests.api.test_ap3_proformas_integrales import payload_integral
from tests.api.test_final_inferred_projection import partial_api as partial_api
from tests.api.test_final_inferred_projection import review
from tests.api.test_final_partial_capture import entry

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize(
    "text,amount",
    [
        ("Una mesa de 500 bolivianos", "500.00"),
        ("Una mesa de madera a mil doscientos cincuenta bolivianos", "1250.00"),
        ("Una mesa de madera de mil bolivianos, perdón, de novecientos bolivianos", "900.00"),
        ("Una mesa, precio de quinientos bolivianos", "500.00"),
    ],
)
def test_price_suggestion_is_useful_but_not_spoken_mode(intake, text, amount):
    result = review(intake, text)
    proposal = result["propuesta_configurador"]
    assert proposal["comercial"]["precio_unitario"] == amount
    assert any(p["codigo"] == "PRECIO_AMBIGUO" for p in proposal["pendientes"])
    assert not any(p["codigo"] == "TOTAL_NEGOCIADO" for p in proposal["pendientes"])


@pytest.mark.parametrize(
    "original,final,state,accepted",
    [
        ("500.00", "500.00", "confirmado", True),
        ("500.00", "550.00", "corregido", True),
        ("500.00", "550.00", "confirmado", False),
        (None, "500.00", "confirmado", False),
        ("999", "500.00", "corregido", False),
    ],
)
def test_saved_confirmation_is_bound_to_server_suggestion(intake, original, final, state, accepted):
    data = entry("Una mesa de 500 bolivianos")
    received = intake.post("/api/v1/capturas/asistidas/", data, format="json")
    assert received.status_code == 202
    assert procesar_intento(intento_id=received.data["intento_id"]) == "FINALIZADO"
    proposal = intake.get(f"/api/v1/capturas/asistidas/{received.data['id']}/").data[
        "propuesta_configurador"
    ]
    index = next(i for i, p in enumerate(proposal["pendientes"]) if p["codigo"] == "PRECIO_AMBIGUO")
    payload = payload_integral(clave=uuid4())
    payload["sesion_borrador"] = data["sesion_borrador"]
    line = payload["detalles"][0]
    line["captura_asistida_id"] = received.data["id"]
    line["precio_unitario"] = final
    line["especificacion"]["datos_tecnicos"] = {
        "revision_humana_voz": [
            {
                "captura_asistida_id": received.data["id"],
                "pendientes_originales": proposal["pendientes"],
                "decisiones": [
                    {
                        "decision_id": str(uuid4()),
                        "review_id": f"pending:{index}",
                        "field": "precio_unitario",
                        "evidence_ids": [],
                        "estado": state,
                        "valor_original": original,
                        "valor_final": final,
                    }
                ],
            }
        ]
    }
    response = intake.post("/api/v1/proformas/integral/", payload, format="json")
    assert response.status_code == (201 if accepted else 400), response.data
    assert Proforma.objects.exists() is accepted
    if accepted:
        saved = EspecificacionMueble.objects.get().datos_tecnicos["revision_humana_voz"]
        decision = saved[0]["decisiones"][0]
        assert decision["estado"] == state
        assert decision["valor_original"] == original
        assert decision["valor_final"] == final
        assert decision["field"] == "precio_unitario"
        assert not IntentoCaptura.objects.get(pk=received.data["intento_id"]).resultado_raw[
            "item_proposal"
        ]["price"]
        repeated = intake.post("/api/v1/proformas/integral/", payload, format="json")
        assert repeated.status_code == 200, repeated.data
        assert Proforma.objects.count() == 1


@pytest.mark.parametrize(
    "text",
    [
        "Dos mesas de 500 bolivianos",
        "Mesa de 500 bolivianos",
        "Mesa con un cajón y precio de 500 bolivianos",
        "Una mesa de 500 dólares",
        "Una mesa de 500 bolivianos o 600 bolivianos",
    ],
)
def test_ambiguous_quantity_or_amount_never_autofills_price(intake, text):
    result = review(intake, text)
    assert result["propuesta_configurador"]["comercial"]["precio_unitario"] is None
