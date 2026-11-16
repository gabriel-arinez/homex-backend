from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.capturas.models import Captura, IntentoCaptura, ItemIA
from apps.capturas.pipeline import procesar_intento
from tests.factories import vendedor

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(params=["catalogo", "asistidas"])
def voice(request, django_user_model, settings, tmp_path):
    settings.HOMEX_AUDIO_TEMP_ROOT = tmp_path
    actor = vendedor(django_user_model.objects.create_user(username="voice"))
    actor.groups.add(Group.objects.get_or_create(name="ENCARGADO_TIENDA")[0])
    api = APIClient()
    api.force_authenticate(actor)
    base = {"sesion_borrador": str(uuid4())}
    base.update({"categoria": "OTRO"} if request.param == "catalogo" else {"moneda_codigo": "BOB"})
    return api, f"/api/v1/capturas/{request.param}/", base


def test_asr_only_then_explicit_text_preserves_audit(voice, monkeypatch):
    api, url, base = voice
    audio = SimpleUploadedFile("voice.wav", b"RIFFstub", content_type="audio/wav")
    received = api.post(
        url,
        {**base, "clave_idempotencia": str(uuid4()), "solo_transcribir": True, "audio": audio},
        format="multipart",
    )
    assert received.status_code == 202, received.data
    monkeypatch.setattr(
        "apps.capturas.catalogo.propuesta_catalogo", lambda *_: pytest.fail("NLP ran")
    )
    monkeypatch.setattr("apps.capturas.pipeline.AdaptadorNLP", lambda: pytest.fail("NLP ran"))
    asr = SimpleNamespace(
        transcribe=lambda _: SimpleNamespace(
            text_original="silla original", latency_ms=1, model_version="test"
        )
    )
    assert (
        procesar_intento(intento_id=received.data["intento_id"], servicio_asr=asr) == "FINALIZADO"
    )
    result = api.get(f"{url}{received.data['id']}/").data
    assert result["estado"] == "COMPLETADA"
    assert result["solo_transcribir"] is True
    assert result["texto_asr_original"] == "silla original"
    assert result.get("propuesta", result.get("propuesta_configurador")) is None
    assert not ItemIA.objects.exists()
    corrected = api.post(
        url,
        {
            **base,
            "clave_idempotencia": str(uuid4()),
            "texto": "silla plegable",
            "captura_origen": received.data["id"],
        },
        format="json",
    )
    assert corrected.status_code == 202, corrected.data
    evidence = api.get(f"{url}{corrected.data['id']}/").data
    assert evidence["texto_asr_original"] == "silla original"
    assert evidence["texto_corregido"] == "silla plegable"
    monkeypatch.undo()
    forbidden_asr = SimpleNamespace(transcribe=lambda _: pytest.fail("ASR ran for text"))
    assert (
        procesar_intento(intento_id=corrected.data["intento_id"], servicio_asr=forbidden_asr)
        == "FINALIZADO"
    )
    assert Captura.objects.get(pk=received.data["id"]).texto_transcrito == "silla original"
    assert IntentoCaptura.objects.get(pk=received.data["intento_id"]).modelo_nlp_version is None


@pytest.mark.parametrize("text", ["", "   ", "12345", "!!!", "💺", "a" * 20001])
def test_reject_unprocessable_text(voice, text):
    api, url, base = voice
    response = api.post(
        url, {**base, "clave_idempotencia": str(uuid4()), "texto": text}, format="json"
    )
    assert response.status_code == 400
    assert not Captura.objects.exists()


def test_short_processable_text_and_asr_flag_guard(voice):
    api, url, base = voice
    data = {**base, "clave_idempotencia": str(uuid4()), "texto": "silla plegable"}
    assert api.post(url, {**data, "solo_transcribir": True}, format="json").status_code == 400
    assert api.post(url, data, format="json").status_code == 202


@pytest.mark.parametrize(
    "seconds,valid",
    [(0, False), (1.99, False), (2, True), (240, True), (300, True), (300.01, False)],
)
def test_decoded_duration_boundaries(monkeypatch, seconds, valid):
    import sys
    from pathlib import Path

    from apps.capturas.audio import AudioTemporalInvalido, validar_duracion_audio

    class Container:
        streams = [SimpleNamespace(type="audio", index=0)]

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def decode(self, **_):
            if seconds:
                yield SimpleNamespace(samples=int(seconds * 1000), sample_rate=1000)

    monkeypatch.setitem(sys.modules, "av", SimpleNamespace(open=lambda _: Container()))
    if valid:
        validar_duracion_audio(Path("decoded.wav"), max_seconds=300)
    else:
        with pytest.raises(AudioTemporalInvalido):
            validar_duracion_audio(Path("decoded.wav"), max_seconds=300)


def test_origin_session_and_owner_are_enforced(voice, django_user_model):
    api, url, base = voice
    data = {**base, "clave_idempotencia": str(uuid4()), "texto": "silla plegable"}
    origin = api.post(url, data, format="json").data["id"]
    linked = {**data, "clave_idempotencia": str(uuid4()), "captura_origen": origin}
    assert (
        api.post(url, {**linked, "sesion_borrador": str(uuid4())}, format="json").status_code == 404
    )
    actor = vendedor(django_user_model.objects.create_user(username="foreign"))
    actor.groups.add(Group.objects.get(name="ENCARGADO_TIENDA"))
    api.force_authenticate(actor)
    assert api.post(url, linked, format="json").status_code == 404


def test_asistida_returns_exact_nlp_candidates(voice):
    api, url, base = voice
    if "asistidas" not in url:
        return
    response = api.post(
        url,
        {
            **base,
            "clave_idempotencia": str(uuid4()),
            "texto": "tres escritorios de 120 cm de largo",
        },
        format="json",
    )
    assert procesar_intento(intento_id=response.data["intento_id"]) == "FINALIZADO"
    raw = IntentoCaptura.objects.get(pk=response.data["intento_id"]).resultado_raw
    result = api.get(f"{url}{response.data['id']}/").data
    assert result["candidatos"] == raw["candidates"]
    assert result["advertencias"] == raw["warnings"]
    assert result["candidatos"]


@pytest.mark.parametrize("transcript", ["", "   ", "!!!", "x" * 20001])
def test_invalid_asr_text_cannot_reach_nlp(voice, monkeypatch, transcript):
    api, url, base = voice
    audio = SimpleUploadedFile("voice.wav", b"RIFFstub", content_type="audio/wav")
    data = {**base, "clave_idempotencia": str(uuid4()), "solo_transcribir": True, "audio": audio}
    received = api.post(url, data, format="multipart")
    assert received.status_code == 202
    asr = SimpleNamespace(
        transcribe=lambda _: SimpleNamespace(
            text_original=transcript, latency_ms=1, model_version="test"
        )
    )
    monkeypatch.setattr(
        "apps.capturas.catalogo.propuesta_catalogo", lambda *_: pytest.fail("NLP ran")
    )
    monkeypatch.setattr("apps.capturas.pipeline.AdaptadorNLP", lambda: pytest.fail("NLP ran"))
    assert procesar_intento(intento_id=received.data["intento_id"], servicio_asr=asr) == "ERROR"
    result = api.get(f"{url}{received.data['id']}/").data
    assert result["estado"] == "ERROR"
    assert result["texto_transcrito_original"] == transcript
    assert result["error_codigo"] == (
        "TRANSCRIPT_TOO_LONG" if len(transcript) > 20000 else "TRANSCRIPT_EMPTY"
    )


def test_audio_stage_is_part_of_idempotency(voice):
    api, url, base = voice
    data = {**base, "clave_idempotencia": str(uuid4()), "solo_transcribir": True}

    def send(**updates):
        return api.post(
            url,
            {
                **data,
                **updates,
                "audio": SimpleUploadedFile("voice.wav", b"RIFFstub", content_type="audio/wav"),
            },
            format="multipart",
        )

    assert send().status_code == 202
    assert send().data["reutilizada"] is True
    assert send(solo_transcribir=False).status_code == 409


def test_real_decoded_wav_minimum_and_long_upload(tmp_path):
    import wave

    from apps.capturas.audio import AudioTemporalInvalido, validar_duracion_audio

    pytest.importorskip("av")
    for seconds in [1, 2, 240, 300]:
        path = tmp_path / f"audio-{seconds}.wav"
        with wave.open(str(path), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(8000)
            stream.writeframes(b"\x00\x00" * 8000 * seconds)
        if seconds < 2:
            with pytest.raises(AudioTemporalInvalido, match="al menos 2"):
                validar_duracion_audio(path, max_seconds=300)
        else:
            validar_duracion_audio(path, max_seconds=300)


def test_successive_text_corrections_keep_original_asr(voice):
    api, url, base = voice
    origin = api.post(
        url,
        {
            **base,
            "clave_idempotencia": str(uuid4()),
            "solo_transcribir": True,
            "audio": SimpleUploadedFile("voice.wav", b"stub", content_type="audio/wav"),
        },
        format="multipart",
    ).data
    asr = SimpleNamespace(
        transcribe=lambda _: SimpleNamespace(
            text_original="silla original", latency_ms=1, model_version="test"
        )
    )
    assert procesar_intento(intento_id=origin["intento_id"], servicio_asr=asr) == "FINALIZADO"
    previous = origin["id"]
    for text in ["silla plegable", "silla roja", "silla azul", "silla verde"]:
        data = {
            **base,
            "clave_idempotencia": str(uuid4()),
            "captura_origen": previous,
            "texto": text,
        }
        response = api.post(url, data, format="json")
        assert response.status_code == 202, response.data
        assert api.post(url, data, format="json").data["reutilizada"] is True
        assert (
            procesar_intento(
                intento_id=response.data["intento_id"],
                servicio_asr=SimpleNamespace(transcribe=lambda _: pytest.fail("ASR repeated")),
            )
            == "FINALIZADO"
        )
        result = api.get(f"{url}{response.data['id']}/").data
        assert result["captura_origen"] == origin["id"]
        assert result["texto_asr_original"] == "silla original"
        assert result["texto_corregido"] == text
        previous = response.data["id"]
    assert Captura.objects.get(pk=origin["id"]).texto_transcrito == "silla original"


@pytest.mark.parametrize("with_asr", [False, True])
def test_historical_text_chain_remains_supported_and_guarded(voice, django_user_model, with_asr):
    api, url, base = voice
    response = api.post(
        url, {**base, "clave_idempotencia": str(uuid4()), "texto": "silla inicial"}, format="json"
    )
    assert response.status_code == 202
    if with_asr:
        response = api.post(
            url,
            {
                **base,
                "clave_idempotencia": str(uuid4()),
                "solo_transcribir": True,
                "audio": SimpleUploadedFile("voice.wav", b"stub", content_type="audio/wav"),
            },
            format="multipart",
        )
        assert response.status_code == 202
        asr = SimpleNamespace(
            transcribe=lambda _: SimpleNamespace(
                text_original="silla inicial", latency_ms=1, model_version="test"
            )
        )
        assert (
            procesar_intento(intento_id=response.data["intento_id"], servicio_asr=asr)
            == "FINALIZADO"
        )
    created = [response.data["id"]]
    # Insert old-client histories with their original links, respecting DB immutability.
    for text in ["silla segunda", "silla tercera"]:
        historical = Captura.objects.get(pk=created[-1])
        historical.pk = None
        historical.clave_idempotencia = uuid4()
        historical.captura_origen_id = created[-1]
        historical.texto_transcrito = text
        historical.save(force_insert=True)
        created.append(historical.pk)
    data = {
        **base,
        "clave_idempotencia": str(uuid4()),
        "texto": "silla final",
        "captura_origen": created[2],
    }
    result = api.post(url, data, format="json")
    assert result.status_code == 202
    assert Captura.objects.get(pk=result.data["id"]).captura_origen_id == (
        created[0] if with_asr else created[2]
    )
    evidence = api.get(f"{url}{result.data['id']}/").data
    assert evidence["texto_asr_original"] == ("silla inicial" if with_asr else None)
    assert evidence["texto_corregido"] == "silla final"
    assert evidence["texto_transcrito_original"] == "silla final"
    assert Captura.objects.get(pk=created[2]).captura_origen_id == created[1]
    before = Captura.objects.count()
    assert api.post(url, {**data, "texto": "otro texto"}, format="json").status_code == 409
    assert Captura.objects.count() == before
    foreign = vendedor(django_user_model.objects.create_user(username="chain-foreign"))
    foreign.groups.add(Group.objects.get(name="ENCARGADO_TIENDA"))
    api.force_authenticate(foreign)
    assert (
        api.post(url, {**data, "clave_idempotencia": str(uuid4())}, format="json").status_code
        == 404
    )
    assert Captura.objects.count() == before


def test_origin_cannot_attach_an_unrelated_audio_execution(voice):
    api, url, base = voice
    origin = api.post(
        url, {**base, "clave_idempotencia": str(uuid4()), "texto": "silla original"}, format="json"
    ).data["id"]
    before = Captura.objects.count()
    response = api.post(
        url,
        {
            **base,
            "clave_idempotencia": str(uuid4()),
            "captura_origen": origin,
            "audio": SimpleUploadedFile("voice.wav", b"stub", content_type="audio/wav"),
        },
        format="multipart",
    )
    assert response.status_code == 400
    assert Captura.objects.count() == before


def test_origin_cycles_are_rejected_without_persistence(voice):
    api, url, base = voice
    origin = api.post(
        url, {**base, "clave_idempotencia": str(uuid4()), "texto": "silla original"}, format="json"
    ).data["id"]
    historical = Captura.objects.get(pk=origin)
    historical.pk = origin + 1000
    historical.clave_idempotencia = uuid4()
    historical.captura_origen_id = historical.pk
    historical.save(force_insert=True)
    origin = historical.pk
    before = Captura.objects.count()
    response = api.post(
        url,
        {
            **base,
            "clave_idempotencia": str(uuid4()),
            "captura_origen": origin,
            "texto": "silla corregida",
        },
        format="json",
    )
    assert response.status_code == 400
    assert Captura.objects.count() == before
