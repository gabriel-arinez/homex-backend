"""Read-only projection must retain scoped accessories without inventing counts."""

from copy import deepcopy
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from apps.capturas.models import Captura, IntentoCaptura, ItemIA
from apps.capturas.nlp.adapter import AdaptadorNLP
from apps.proformas.services import crear_proforma
from tests.factories import cliente_persona, vendedor


@pytest.fixture
def scoped_capture(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="accessory-review"))
    quote = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    client = APIClient()
    client.force_authenticate(actor)

    def response_for(scope, quantity, multiple=False):
        text = (
            "Dos escritorios con casillero y dos USB"
            + (" y tres HDMI" if multiple else "")
            + ". Precio unitario 100 bolivianos."
        )
        created = client.post(
            "/api/v1/capturas/",
            {"clave_idempotencia": str(uuid4()), "proforma": quote.id, "texto": text},
            format="json",
        )
        assert created.status_code == 202
        attempt = IntentoCaptura.objects.get(pk=created.data["intento_id"])
        raw = (
            AdaptadorNLP()
            .extraer(solicitud_id="scoped-accessory", texto=text, moneda="BOB")
            .resultado_original
        )
        component = next(c for c in raw["item_proposal"]["components"] if c["name"] == "casillero")
        accessories = raw["item_proposal"]["accessories"]
        assert len(accessories) == (2 if multiple else 1)
        # Explicit producer-contract fixture: test the backend's routing, not
        # whether an acoustic or syntactic component relationship is true.
        for accessory in accessories:
            accessory["component_ref"] = (
                component["component_id"]
                if scope == "component"
                else "missing-piece"
                if scope == "unknown"
                else None
            )
            if not multiple:
                accessory["quantity"] = quantity
        attempt.resultado_raw = raw
        attempt.estado = "FINALIZADO"
        attempt.save()
        ItemIA.objects.create(intento=attempt, nombre="Escritorios", cantidad=2, precio_total="200")
        Captura.objects.filter(pk=created.data["id"]).update(estado="COMPLETADA")
        original = deepcopy(raw)
        result = client.get(f"/api/v1/capturas/{created.data['id']}/")
        assert result.status_code == 200
        attempt.refresh_from_db()
        quote.refresh_from_db()
        assert attempt.resultado_raw == original
        assert quote.estado.codigo == "BORRADOR" and not quote.detalles.exists()
        return result.data

    return response_for


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("scope", ["component", "global", "unknown"])
@pytest.mark.parametrize("quantity", [2, None])
def test_accessory_scope_and_absent_quantity_are_not_discarded(scoped_capture, scope, quantity):
    response = scoped_capture(scope, quantity)
    projection = response["proyeccion_configurador"]
    if scope == "unknown" and response["proyeccion_error"]:
        assert projection is None
        return
    assert not response["proyeccion_error"]
    data = projection["especificacion"]["datos_tecnicos"]
    rendered = "2 USB" if quantity == 2 else "USB"
    if scope == "component":
        assert data["accesorios"] == []
        assert data["componentes"][0]["atributos"] == [{"nombre": "Accesorios", "valor": rendered}]
    elif scope == "global":
        assert data["accesorios"] == [rendered]
        assert not data["componentes"][0].get("atributos")
    else:
        assert data["accesorios"] == []
        assert not data["componentes"][0].get("atributos")
        assert any(rendered in p["mensaje"] for p in projection["pendientes"])


@pytest.mark.django_db(transaction=True)
def test_multiple_scoped_accessories_share_one_valid_attribute_without_summing(scoped_capture):
    response = scoped_capture("component", 2, multiple=True)
    data = response["proyeccion_configurador"]["especificacion"]["datos_tecnicos"]
    assert data["accesorios"] == []
    assert data["componentes"][0]["atributos"] == [
        {"nombre": "Accesorios", "valor": "2 USB; 3 HDMI"}
    ]
