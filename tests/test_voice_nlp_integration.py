"""Integration coverage against the exact vendored NLP wheel, never a source override."""

from uuid import uuid4

import homex_nlp
import pytest
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from apps.capturas.models import IntentoCaptura
from apps.capturas.pipeline import procesar_intento
from tests.factories import vendedor

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def client(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="wheel-integration"))
    actor.groups.add(Group.objects.get_or_create(name="ENCARGADO_TIENDA")[0])
    api = APIClient()
    api.force_authenticate(actor)
    return api


def process(client, mode, text, category="OTRO"):
    context = {"categoria": category} if mode == "catalogo" else {"moneda_codigo": "BOB"}
    response = client.post(
        f"/api/v1/capturas/{mode}/",
        {
            "clave_idempotencia": str(uuid4()),
            "sesion_borrador": str(uuid4()),
            "texto": text,
            **context,
        },
        format="json",
    )
    assert response.status_code == 202, response.data
    assert procesar_intento(intento_id=response.data["intento_id"]) == "FINALIZADO"
    return client.get(
        f"/api/v1/capturas/{mode}/{response.data['id']}/"
    ).data, IntentoCaptura.objects.get(pk=response.data["intento_id"]).resultado_raw


@pytest.mark.parametrize(
    "text",
    [
        "hola buenas",
        "probando",
        "uno dos tres",
        "hola 123",
        "probando123",
        "probando 123",
        "hola precio",
        "probando color",
        "hola marca",
    ],
)
def test_catalog_chatter_abstains_in_actual_wheel(client, text):
    result, _ = process(client, "catalogo", text)
    assert result["propuesta"]["fields"] == {}
    assert result["texto_transcrito_original"] == text


def test_short_catalog_name_remains_valid(client):
    result, _ = process(client, "catalogo", "silla plegable", "SILLA")
    assert result["propuesta"]["fields"]["nombre"] == "silla plegable"


@pytest.mark.parametrize("text", ["mueble", "un mueble", "hola buenas"])
def test_bare_furniture_abstains_in_actual_wheel(client, text):
    result, raw = process(client, "asistidas", text)
    assert raw["item_proposal"] is None
    assert result["resultado"] == "NO_PROPOSAL"
    assert result["propuesta_configurador"] is None


def test_described_generic_furniture_remains_valid(client):
    result, raw = process(client, "asistidas", "Un mueble de melamina con dos cajones.")
    assert raw["item_proposal"] is not None
    assert result["candidatos"] == raw["candidates"]


def test_currency_rejection_preserves_actual_span_with_unresolved_decision(client):
    text = "nombre: Silla Gamer; precio 300 dólares"
    result, _ = process(client, "catalogo", text, "SILLA")
    assert "precio_lista" not in result["propuesta"]["fields"]
    price = [e for e in result["propuesta"]["evidence"] if e["label"] == "precio_lista"]
    assert price
    for evidence in price:
        assert evidence["decision"] == "UNRESOLVED"
        assert evidence["reason"]
        assert text[evidence["start"] : evidence["end"]] == evidence["text"]


def test_installed_nlp_runtime_matches_new_vendored_release():
    assert homex_nlp.__version__ == "0.1.28"


def test_audio_minimum_cannot_be_configured_below_two_seconds(monkeypatch):
    import sys
    from pathlib import Path
    from types import SimpleNamespace

    from apps.capturas.audio import AudioTemporalInvalido, validar_duracion_audio

    class Container:
        streams = [SimpleNamespace(type="audio", index=0)]

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def decode(self, **_):
            yield SimpleNamespace(samples=1000, sample_rate=1000)

    monkeypatch.setitem(sys.modules, "av", SimpleNamespace(open=lambda _: Container()))
    with pytest.raises(AudioTemporalInvalido, match="al menos 2"):
        validar_duracion_audio(Path("one-second.wav"), max_seconds=300, min_seconds=0)


@pytest.mark.parametrize(
    "text,name",
    [
        ("nombre: Credenza Nórdica", "Credenza Nórdica"),
        ("nombre comercial: Organizador Koru artesanal", "Organizador Koru artesanal"),
    ],
)
def test_explicit_unknown_name_preserves_exact_original_text(client, text, name):
    result, _ = process(client, "catalogo", text)
    assert result["propuesta"]["fields"]["nombre"] == name
    assert result["texto_transcrito_original"] == text
    names = [e for e in result["propuesta"]["evidence"] if e["label"] == "nombre"]
    assert names
    for evidence in names:
        assert evidence["decision"] == "ACCEPTED"
        assert text[evidence["start"] : evidence["end"]] == evidence["text"]
