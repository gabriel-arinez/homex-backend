"""Synthetic API/pipeline regressions; never uses private ASR recordings."""

from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from apps.capturas.models import IntentoCaptura
from apps.capturas.pipeline import procesar_intento
from apps.proformas.models import DetalleProforma, Proforma
from tests.factories import vendedor

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize("amount", ["10 mil", "diez mil", "10.000", "10000", "10"])
@pytest.mark.parametrize("mode", ["unitario", "total negociado"])
def test_equivalent_amount_api_pipeline_projection(django_user_model, amount, mode):
    actor = vendedor(django_user_model.objects.create_user(username="money-correction"))
    api = APIClient()
    api.force_authenticate(actor)
    text = f"Tres mesas de taller de 0.20 metros de ancho. Precio {mode} {amount} bolivianos."
    entry = {
        "clave_idempotencia": str(uuid4()),
        "sesion_borrador": str(uuid4()),
        "moneda_codigo": "BOB",
        "texto": text,
    }
    response = api.post("/api/v1/capturas/asistidas/", entry, format="json")
    assert response.status_code == 202, response.data
    attempt_id = response.data["intento_id"]
    assert procesar_intento(intento_id=attempt_id) == "FINALIZADO"
    attempt = IntentoCaptura.objects.get(pk=attempt_id)
    expected = "10.00" if amount == "10" else "10000.00"
    raw = attempt.resultado_raw
    assert raw["text_original"] == text
    assert raw["item_proposal"]["price"]["stated_amount"] == expected
    assert raw["item_proposal"]["price"]["currency"] == "BOB"
    assert raw["item_proposal"]["price"]["component_ref"] is None
    assert raw["item_proposal"]["dimensions"][0]["value"] == "0.20"
    read = api.get(f"/api/v1/capturas/asistidas/{response.data['id']}/")
    assert read.status_code == 200
    projection = read.data["propuesta_configurador"]
    if mode == "unitario":
        assert projection["comercial"]["precio_unitario"] == expected
    else:
        assert projection["comercial"]["precio_unitario"] is None
        pending = next(x for x in projection["pendientes"] if x["codigo"] == "TOTAL_NEGOCIADO")
        assert pending["total_negociado"] == expected
    assert api.post("/api/v1/capturas/asistidas/", entry, format="json").data["reutilizada"]
    assert Proforma.objects.count() == DetalleProforma.objects.count() == 0
