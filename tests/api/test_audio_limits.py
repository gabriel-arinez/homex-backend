"""Límites de audio que protegen el ASR y la carga comercial."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.capturas.audio import AudioTemporalInvalido, hash_audio, validar_duracion_audio


def test_rechaza_tamano_sobre_limite_sin_retener_audio():
    with override_settings(HOMEX_AUDIO_MAX_BYTES=5):
        with pytest.raises(AudioTemporalInvalido, match="límite"):
            hash_audio(SimpleUploadedFile("test.wav", b"123456"))
        assert hash_audio(SimpleUploadedFile("test.wav", b"12345"))


@pytest.mark.parametrize(
    ("samples", "ok"),
    [(30_000, True), (30_001, False)],
)
def test_worker_rechaza_duracion_superior_a_cinco_minutos(monkeypatch, samples, ok):
    class Container:
        streams = [SimpleNamespace(type="audio", index=0)]

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def decode(self, *, audio):
            assert audio == 0
            yield SimpleNamespace(samples=samples, sample_rate=100)

    monkeypatch.setitem(sys.modules, "av", SimpleNamespace(open=lambda _: Container()))
    if ok:
        validar_duracion_audio(Path("audio.webm"), max_seconds=300)
    else:
        with pytest.raises(AudioTemporalInvalido, match="minutos"):
            validar_duracion_audio(Path("audio.webm"), max_seconds=300)


def test_worker_rechaza_audio_sin_fotogramas(monkeypatch):
    class Container:
        streams = [SimpleNamespace(type="audio", index=0)]

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def decode(self, *, audio):
            return iter(())

    monkeypatch.setitem(sys.modules, "av", SimpleNamespace(open=lambda _: Container()))
    with pytest.raises(AudioTemporalInvalido, match="decodificable"):
        validar_duracion_audio(Path("vacio.ogg"), max_seconds=300)
