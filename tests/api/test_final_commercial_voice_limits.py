"""Commercial intake bounds preserve final-lote02 partial extraction (S2/S12)."""

import io
import wave
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import ValidationError

from apps.capturas.limites import validar_texto_comercial
from apps.capturas.models import Captura, IntentoCaptura, TrabajoOutbox
from tests.api.test_voice_transcription_review import voice  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def words(count):
    return " ".join(f"dato{i}" for i in range(count))


@pytest.mark.parametrize("count,valid", [(0, False), (19, True), (20, True), (21, True)])
def test_word_boundary(voice, count, valid):  # noqa: F811
    api, url, base = voice
    result = api.post(
        url, {**base, "clave_idempotencia": str(uuid4()), "texto": words(count)}, format="json"
    )
    assert result.status_code == (202 if valid else 400), result.data
    assert Captura.objects.count() == int(valid)
    assert IntentoCaptura.objects.count() == int(valid)


@pytest.mark.parametrize("length", [2999, 3000, 3001])
def test_character_boundary(voice, length):  # noqa: F811
    api, url, base = voice
    text = words(20) + "x" * (length - len(words(20)))
    result = api.post(
        url, {**base, "clave_idempotencia": str(uuid4()), "texto": text}, format="json"
    )
    assert result.status_code == (202 if length <= 3000 else 400), result.data
    assert Captura.objects.exists() == (length <= 3000)


def test_words_ignore_punctuation_and_keep_normalized_measures():
    # S2/S12 replace minimum-word policy with processable letter-bearing text.
    validar_texto_comercial(words(19) + " ... — / ")
    for text in ("", "  ", "12345", "... — / "):
        with pytest.raises(ValidationError):
            validar_texto_comercial(text)
    validar_texto_comercial(words(18) + " 18mm 1,5m")


@pytest.mark.parametrize(
    "seconds,valid",
    [(14, False), (15, True), (16, True), (240, True), (241, True), (300, True), (301, False)],
)
def test_decoded_audio_before_capture_or_outbox(voice, seconds, valid, monkeypatch):  # noqa: F811
    api, url, base = voice
    data = io.BytesIO()
    with wave.open(data, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\0\0" * 8000 * seconds)
    monkeypatch.setattr(
        "apps.capturas.pipeline.construir_servicio_asr",
        lambda: pytest.fail("Whisper constructed during reception"),
    )
    result = api.post(
        url,
        {
            **base,
            "clave_idempotencia": str(uuid4()),
            "solo_transcribir": True,
            "audio": SimpleUploadedFile("voice.wav", data.getvalue(), content_type="audio/wav"),
        },
        format="multipart",
    )
    assert result.status_code == (202 if valid else 400), result.data
    assert Captura.objects.count() == int(valid)
    assert IntentoCaptura.objects.count() == int(valid)
    assert TrabajoOutbox.objects.count() == int(valid)


@pytest.mark.parametrize(
    "contents,name",
    [
        (b"", "empty.wav"),
        (b"not audio", "broken.wav"),
        (b"not audio", "file.exe"),
        (b"x" * 20_000_001, "large.wav"),
    ],
)
def test_invalid_audio_creates_no_processing_work(voice, contents, name, monkeypatch):  # noqa: F811
    api, url, base = voice
    monkeypatch.setattr(
        "apps.capturas.pipeline.construir_servicio_asr", lambda: pytest.fail("Whisper started")
    )
    response = api.post(
        url,
        {
            **base,
            "clave_idempotencia": str(uuid4()),
            "solo_transcribir": True,
            "audio": SimpleUploadedFile(name, contents, content_type="audio/wav"),
        },
        format="multipart",
    )
    assert response.status_code == 400, response.data
    assert not Captura.objects.exists()
    assert not IntentoCaptura.objects.exists()
    assert not TrabajoOutbox.objects.exists()


def test_asr_over_commercial_limit_is_preserved_without_nlp(voice, monkeypatch):  # noqa: F811
    from types import SimpleNamespace

    from apps.capturas.pipeline import procesar_intento
    from tests.factories import commercial_voice_audio

    api, url, base = voice
    response = api.post(
        url,
        {
            **base,
            "clave_idempotencia": str(uuid4()),
            "solo_transcribir": True,
            "audio": commercial_voice_audio(),
        },
        format="multipart",
    )
    assert response.status_code == 202, response.data
    text = "silla " * 501
    monkeypatch.setattr(
        "apps.capturas.catalogo.propuesta_catalogo", lambda *_: pytest.fail("NLP started")
    )
    monkeypatch.setattr("apps.capturas.pipeline.AdaptadorNLP", lambda: pytest.fail("NLP started"))
    service = SimpleNamespace(
        transcribe=lambda _: SimpleNamespace(
            text_original=text, latency_ms=1, model_version="fixture"
        )
    )
    assert (
        procesar_intento(intento_id=response.data["intento_id"], servicio_asr=service)
        == "FINALIZADO"
    )
    result = api.get(f"{url}{response.data['id']}/").data
    assert result["texto_asr_original"] == text
    assert result["texto_transcrito_original"] == text
    assert result["estado"] == "COMPLETADA"
    rejected = api.post(
        url,
        {
            **base,
            "clave_idempotencia": str(uuid4()),
            "texto": text,
            "captura_origen": response.data["id"],
        },
        format="json",
    )
    assert rejected.status_code == 400
    assert Captura.objects.count() == 1
