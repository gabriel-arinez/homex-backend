"""One review response must preserve one selected attempt and explicit failures."""

from copy import deepcopy
from uuid import uuid4

import pytest
from django.db.models import QuerySet
from homex_nlp.contracts import ExtractionResult
from rest_framework.test import APIClient

from apps.capturas.api.serializers import CapturaRevisionSerializer
from apps.capturas.models import IntentoCaptura, ItemIA
from apps.capturas.nlp.adapter import AdaptadorNLP
from apps.capturas.proyeccion_prf03 import VERSION_PROYECCION
from apps.capturas.services import crear_intento, recibir_captura_texto
from apps.proformas.services import crear_proforma
from tests.factories import cliente_persona, vendedor


def scenario(users):
    actor = vendedor(users.objects.create_user(username="premerge-review"))
    quote = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    receipt = recibir_captura_texto(
        actor=actor,
        clave_idempotencia=uuid4(),
        proforma_id=quote.id,
        texto="Un escritorio con casillero",
    )
    client = APIClient()
    client.force_authenticate(actor)
    return actor, quote, receipt, client


_SAME_OBSERVATIONS = object()


def finish(
    attempt,
    name="Original",
    observations="Original note",
    invalid_technical=False,
    legacy_observations=_SAME_OBSERVATIONS,
):
    raw = (
        AdaptadorNLP()
        .extraer(
            solicitud_id=f"attempt-{attempt.id}", texto="Un escritorio con casillero", moneda="BOB"
        )
        .resultado_original
    )
    raw["item_proposal"]["name"] = name
    raw["item_proposal"]["observations"] = observations
    if invalid_technical:
        raw["item_proposal"]["components"][0]["name"] = "x" * 201
    attempt.resultado_raw = raw
    attempt.estado = "FINALIZADO"
    attempt.save()
    return ItemIA.objects.create(
        intento=attempt,
        nombre=name,
        cantidad=1,
        observaciones=(
            observations if legacy_observations is _SAME_OBSERVATIONS else legacy_observations
        ),
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("initially_finalized", [True, False])
def test_response_selects_one_attempt_even_when_another_finalizes_between_getters(
    django_user_model, monkeypatch, initially_finalized
):
    _, _, receipt, _ = scenario(django_user_model)
    item = finish(receipt.intento) if initially_finalized else None
    original_first = QuerySet.first
    selected = []
    newer = []

    def first(queryset):
        result = original_first(queryset)
        if queryset.model is IntentoCaptura and queryset._fields is None:
            selected.append(result.pk if result else None)
            if not newer:
                attempt = crear_intento(captura_id=receipt.captura.id, input_hash="new-input")
                newer.append(finish(attempt, "New proposal", "New note"))
        return result

    monkeypatch.setattr(QuerySet, "first", first)
    serializer = CapturaRevisionSerializer()
    response = serializer.to_representation(receipt.captura)
    assert response["intento_id"] == (receipt.intento.id if initially_finalized else None)
    assert response["item_ia"] == (
        None
        if item is None
        else dict(
            id=item.id,
            nombre=item.nombre,
            espesor=None,
            color_principal=None,
            color_secundario=None,
            dimensiones=None,
            accesorios=None,
            cantidad=1,
            precio_total=None,
            observaciones=item.observaciones,
        )
    )
    assert (
        response["proyeccion_configurador"] is None
        if item is None
        else response["proyeccion_configurador"]["comercial"]["nombre"] == item.nombre
    )
    assert len(selected) == 1
    # Reusing the serializer for another representation must take a fresh snapshot.
    next_response = serializer.to_representation(receipt.captura)
    assert next_response["intento_id"] == newer[0].intento_id
    assert next_response["item_ia"]["id"] == newer[0].id
    assert next_response["proyeccion_configurador"]["especificacion"]["observaciones"] == "New note"


@pytest.mark.django_db(transaction=True)
def test_nlp_valid_but_technically_invalid_evidence_is_explicit_read_only_fallback(
    django_user_model,
):
    _, quote, receipt, client = scenario(django_user_model)
    finish(receipt.intento, invalid_technical=True)
    raw = deepcopy(receipt.intento.resultado_raw)
    ExtractionResult.model_validate(raw)
    response = client.get(f"/api/v1/capturas/{receipt.captura.id}/")
    assert response.status_code == 200
    assert response.data["proyeccion_configurador"] is None
    assert response.data["proyeccion_error"] is True
    receipt.intento.refresh_from_db()
    assert receipt.intento.resultado_raw == raw
    assert not quote.detalles.exists()


@pytest.mark.django_db(transaction=True)
def test_projection_version_reaches_public_legacy_review(django_user_model):
    _, _, receipt, client = scenario(django_user_model)
    finish(receipt.intento)
    response = client.get(f"/api/v1/capturas/{receipt.captura.id}/")
    assert response.status_code == 200
    assert response.data["proyeccion_configurador"]["version_proyeccion"] == VERSION_PROYECCION


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "projected,legacy",
    [
        ("Structured note", "Older materialized note"),
        ("Structured note", None),
        (None, "Older materialized note"),
    ],
)
def test_valid_public_review_keeps_independently_persisted_observation_representations(
    django_user_model, projected, legacy
):
    _, quote, receipt, client = scenario(django_user_model)
    item = finish(receipt.intento, observations=projected, legacy_observations=legacy)
    ExtractionResult.model_validate(receipt.intento.resultado_raw)
    response = client.get(f"/api/v1/capturas/{receipt.captura.id}/")
    assert response.status_code == 200
    assert not response.data["proyeccion_error"]
    assert response.data["item_ia"]["observaciones"] == legacy
    assert response.data["proyeccion_configurador"]["especificacion"]["observaciones"] == projected
    item.refresh_from_db()
    assert item.observaciones == legacy
    assert not quote.detalles.exists()
