"""Partial extraction accepts short text without relaxing commercial persistence."""

from uuid import uuid4

import pytest
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from apps.capturas.models import Captura, IntentoCaptura, RevisionAsistida
from apps.capturas.pipeline import procesar_intento
from apps.catalogo.models import Producto
from apps.clientes.models import Cliente
from apps.proformas.models import DetalleProforma, Proforma
from tests.api.test_ap3_proformas_integrales import payload_integral
from tests.factories import vendedor

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def intake(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="partial-intake"))
    actor.groups.add(Group.objects.get_or_create(name="ENCARGADO_TIENDA")[0])
    api = APIClient()
    api.force_authenticate(actor)
    return api


def entry(text):
    return {
        "clave_idempotencia": str(uuid4()),
        "sesion_borrador": str(uuid4()),
        "moneda_codigo": "BOB",
        "texto": text,
    }


@pytest.mark.parametrize(
    "text,identity,quantity",
    [
        ("una mesa", "mesa", 1),
        ("una mesa simple", "mesa", 1),
        ("tres escritorios blancos", "escritorio", 3),
        ("un mueble de melamina", "mueble", 1),
    ],
)
def test_partial_identity_round_trip_does_not_fabricate_or_save(intake, text, identity, quantity):
    data = entry(text)
    received = intake.post("/api/v1/capturas/asistidas/", data, format="json")
    assert received.status_code == 202, received.data
    assert procesar_intento(intento_id=received.data["intento_id"]) == "FINALIZADO"
    response = intake.get(f"/api/v1/capturas/asistidas/{received.data['id']}/")
    assert response.status_code == 200, response.data
    result = response.data
    assert result["texto_transcrito_original"] == text
    assert Captura.objects.get(pk=received.data["id"]).texto_transcrito == text
    assert result["resultado"] == "REQUIRES_REVIEW", result
    proposal = result["propuesta_configurador"]
    assert identity.casefold() in proposal["comercial"]["nombre"].casefold()
    assert proposal["comercial"]["cantidad"] == quantity
    assert proposal["comercial"]["precio_unitario"] is None
    technical = proposal["especificacion"]["datos_tecnicos"]
    assert not technical.get("dimensiones"), technical
    for component in technical.get("componentes", []):
        assert not component.get("dimensiones"), component
        if "melamina" not in text:
            assert not component.get("material"), component
        if "blancos" not in text:
            assert not component.get("color"), component
    assert not any(
        model.objects.exists() for model in (Producto, Cliente, Proforma, DetalleProforma)
    )
    # Extraction is not final commercial validation: absent price must still block saving.
    payload = payload_integral(clave=uuid4())
    payload["sesion_borrador"] = data["sesion_borrador"]
    detail = payload["detalles"][0]
    detail.update(
        captura_asistida_id=received.data["id"],
        nombre=proposal["comercial"]["nombre"],
        precio_unitario=None,
        especificacion=proposal["especificacion"],
    )
    rejected = intake.post("/api/v1/proformas/integral/", payload, format="json")
    assert rejected.status_code == 400, rejected.data
    assert not any(
        model.objects.exists() for model in (Cliente, Proforma, DetalleProforma, RevisionAsistida)
    )
    replay = intake.post("/api/v1/capturas/asistidas/", data, format="json")
    assert replay.status_code == 202 and replay.data["reutilizada"] is True
    assert Captura.objects.count() == IntentoCaptura.objects.count() == 1
    changed = intake.post(
        "/api/v1/capturas/asistidas/", data | {"texto": text + " azul"}, format="json"
    )
    assert changed.status_code == 409, changed.data


def test_greeting_is_processed_without_commercial_proposal(intake):
    text = "Hola buenos días, estamos probando el micrófono"
    received = intake.post("/api/v1/capturas/asistidas/", entry(text), format="json")
    assert received.status_code == 202, received.data
    assert procesar_intento(intento_id=received.data["intento_id"]) == "FINALIZADO"
    result = intake.get(f"/api/v1/capturas/asistidas/{received.data['id']}/").data
    assert result["texto_transcrito_original"] == text
    assert result["resultado"] == "NO_PROPOSAL", result
    assert result["propuesta_configurador"] is None
    assert not Producto.objects.exists()
    assert not Proforma.objects.exists()


@pytest.mark.parametrize("route", ["asistidas", "catalogo"])
@pytest.mark.parametrize(
    "text,accepted",
    [
        ("á", True),
        ("", False),
        ("  ", False),
        ("123", False),
        ("!!!", False),
        ("a" * 3000, True),
        ("a" * 3001, False),
    ],
)
def test_shared_intake_keeps_text_and_size_boundaries(intake, route, text, accepted):
    data = entry(text)
    if route == "catalogo":
        data.pop("moneda_codigo")
        data["categoria"] = "OTRO"
    response = intake.post(f"/api/v1/capturas/{route}/", data, format="json")
    assert response.status_code == (202 if accepted else 400), response.data
    assert Captura.objects.count() == int(accepted)
    assert IntentoCaptura.objects.count() == int(accepted)


def test_partial_intake_requires_authenticated_commercial_user():
    response = APIClient().post("/api/v1/capturas/asistidas/", entry("mesa"), format="json")
    assert response.status_code in {401, 403}
    assert not Captura.objects.exists()
