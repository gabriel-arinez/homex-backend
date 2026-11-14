"""Public capture input must honor the installed NLP transcript boundary."""

from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from apps.capturas.models import Captura, IntentoCaptura, TrabajoOutbox
from apps.proformas.services import crear_proforma
from tests.factories import cliente_persona, vendedor


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("format", ["json", "multipart"])
@pytest.mark.parametrize("length,expected_status", [(20_000, 202), (20_001, 400)])
def test_capture_text_limit_rejects_without_persisting_or_truncating(
    django_user_model, format, length, expected_status
):
    actor = vendedor(django_user_model.objects.create_user(username="transcript-boundary"))
    quote = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    client = APIClient()
    client.force_authenticate(actor)
    text = ("Un escritorio de melamina. " + "Acabado blanco. " * 1500)[:length]
    assert len(text) == length
    response = client.post(
        "/api/v1/capturas/",
        {"clave_idempotencia": str(uuid4()), "proforma": quote.id, "texto": text},
        format=format,
    )
    assert response.status_code == expected_status
    if expected_status == 400:
        assert "texto" in response.data
        assert not Captura.objects.exists()
        assert not IntentoCaptura.objects.exists()
        assert not TrabajoOutbox.objects.exists()
    else:
        assert Captura.objects.get(pk=response.data["id"]).texto_transcrito == text
        assert (
            Captura.objects.count()
            == IntentoCaptura.objects.count()
            == TrabajoOutbox.objects.count()
            == 1
        )


def test_installed_nlp_and_public_text_serializers_share_the_boundary():
    from homex_nlp.contracts import ExtractionRequest

    from apps.capturas.api.serializers import CrearCapturaSerializer, CrearCapturaTextoSerializer

    limit = ExtractionRequest.model_json_schema()["properties"]["text"]["maxLength"]
    assert limit == 20_000
    assert CrearCapturaSerializer().fields["texto"].max_length == limit
    assert CrearCapturaTextoSerializer().fields["texto"].max_length == limit
