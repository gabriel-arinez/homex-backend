"""Regresiones del ciclo de vida ASR; no carga pesos ni requiere Celery/DB."""

from unittest.mock import Mock

import pytest
from django.test import override_settings

from apps.capturas import asr


@pytest.fixture(autouse=True)
def reset_asr_cache(monkeypatch):
    monkeypatch.setattr(asr, "_cached_pid", None)
    monkeypatch.setattr(asr, "_cached_config", None)
    monkeypatch.setattr(asr, "_cached_transcriptor", None)


@pytest.fixture
def model_settings(tmp_path):
    model_dir = tmp_path / "modelo-v15"
    model_dir.mkdir()
    with override_settings(
        HOMEX_ASR_MODEL_PATH=str(model_dir),
        HOMEX_ASR_DEVICE="cpu",
        HOMEX_ASR_COMPUTE_TYPE="int8",
        HOMEX_AUDIO_MAX_BYTES=25000000,
    ):
        yield model_dir


def test_reutiliza_en_mismo_proceso(model_settings, monkeypatch):
    constructor = Mock()
    monkeypatch.setattr(asr, "TranscriptorFasterWhisper", constructor)
    first = asr.construir_servicio_asr()
    second = asr.construir_servicio_asr()
    assert first is not second
    assert first._transcriber is second._transcriber
    constructor.assert_called_once_with(model_settings, device="cpu", compute_type="int8")


def test_invalida_ante_cambio_de_configuracion(model_settings, monkeypatch):
    constructor = Mock()
    monkeypatch.setattr(asr, "TranscriptorFasterWhisper", constructor)
    asr.construir_servicio_asr()
    with override_settings(HOMEX_ASR_COMPUTE_TYPE="float32"):
        asr.construir_servicio_asr()
    asr.construir_servicio_asr()
    assert constructor.call_count == 3


def test_nunca_reutiliza_modelo_heredado_de_otro_pid(model_settings, monkeypatch):
    primero, segundo = Mock(), Mock()
    constructor = Mock(side_effect=[primero, segundo])
    monkeypatch.setattr(asr, "TranscriptorFasterWhisper", constructor)
    monkeypatch.setattr(asr.os, "getpid", Mock(side_effect=[100, 101]))
    a = asr.construir_servicio_asr()
    b = asr.construir_servicio_asr()
    assert a._transcriber is primero
    assert b._transcriber is segundo
    assert constructor.call_count == 2


def test_fallo_de_carga_no_contamina_cache(model_settings, monkeypatch):
    model = Mock()
    constructor = Mock(side_effect=[RuntimeError("modelo defectuoso"), model])
    monkeypatch.setattr(asr, "TranscriptorFasterWhisper", constructor)
    with pytest.raises(RuntimeError, match="modelo defectuoso"):
        asr.construir_servicio_asr()
    result = asr.construir_servicio_asr()
    assert result._transcriber is model
    assert constructor.call_count == 2


def test_modelo_desaparecido_no_reutiliza_cache(model_settings, monkeypatch):
    constructor = Mock()
    monkeypatch.setattr(asr, "TranscriptorFasterWhisper", constructor)
    asr.construir_servicio_asr()
    model_settings.rmdir()
    with pytest.raises(Exception):
        asr.construir_servicio_asr()
    assert constructor.call_count == 1


def test_sin_ruta_no_carga_modelo(monkeypatch):
    constructor = Mock()
    monkeypatch.setattr(asr, "TranscriptorFasterWhisper", constructor)
    with override_settings(HOMEX_ASR_MODEL_PATH=""):
        with pytest.raises(Exception):
            asr.construir_servicio_asr()
    constructor.assert_not_called()
