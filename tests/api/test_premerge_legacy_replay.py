"""A historical receipt is replayable, not a way to create oversized requests."""

from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from apps.capturas.models import Captura, IntentoCaptura, TrabajoOutbox
from apps.capturas.services import recibir_captura_texto
from apps.proformas.services import crear_proforma
from tests.factories import cliente_persona, vendedor


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("format", ["json", "multipart"])
@pytest.mark.parametrize("change", [None, "actor", "quote", "detail", "text", "key"])
def test_oversized_historical_replay_preserves_exact_authorized_identity(
    django_user_model, format, change
):
    actor = vendedor(django_user_model.objects.create_user(username="historical-owner"))
    quote = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    text = "Un escritorio. " + "x" * 20000
    key = uuid4()
    # Existing persisted state from the pre-limit contract, not a new HTTP request.
    receipt = recibir_captura_texto(
        actor=actor, clave_idempotencia=key, proforma_id=quote.id, texto=text
    )
    payload = {"clave_idempotencia": str(key), "proforma": quote.id, "texto": text}
    if change == "actor":
        actor = vendedor(django_user_model.objects.create_user(username="historical-other"))
    elif change == "quote":
        payload["proforma"] = crear_proforma(
            actor=actor, cliente=cliente_persona(actor, sufijo="other")
        ).id
    elif change == "detail":
        payload["proforma_detalle"] = 999999
    elif change == "text":
        payload["texto"] += " changed"
    elif change == "key":
        payload["clave_idempotencia"] = str(uuid4())
    client = APIClient()
    client.force_authenticate(actor)
    response = client.post("/api/v1/capturas/", payload, format=format)
    assert response.status_code == (202 if change is None else 400 if change == "key" else 409)
    if change is None:
        assert response.data["id"] == receipt.captura.id
        assert response.data["intento_id"] == receipt.intento.id
        assert response.data["reutilizada"] is True
    assert (
        Captura.objects.count()
        == IntentoCaptura.objects.count()
        == TrabajoOutbox.objects.count()
        == 1
    )
    receipt.captura.refresh_from_db()
    assert receipt.captura.texto_transcrito == text
