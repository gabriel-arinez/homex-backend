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
    model_settings.mkdir()
    asr.construir_servicio_asr()
    assert constructor.call_count == 2


def test_sin_ruta_no_carga_modelo(monkeypatch):
    constructor = Mock()
    monkeypatch.setattr(asr, "TranscriptorFasterWhisper", constructor)
    with override_settings(HOMEX_ASR_MODEL_PATH=""):
        with pytest.raises(Exception):
            asr.construir_servicio_asr()
    constructor.assert_not_called()


def test_hilos_cargan_una_sola_vez(model_settings, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    constructor = Mock()
    monkeypatch.setattr(asr, "TranscriptorFasterWhisper", constructor)
    with ThreadPoolExecutor(max_workers=4) as pool:
        modelos = list(pool.map(lambda _: asr._obtener_transcriptor(), range(12)))
    assert all(m is modelos[0] for m in modelos)
    assert constructor.call_count == 1


def test_fork_real_descarta_lock_heredado(model_settings, monkeypatch):
    import os
    import select

    monkeypatch.setattr(asr, "TranscriptorFasterWhisper", Mock())
    asr._obtener_transcriptor()
    read_fd, write_fd = os.pipe()
    asr._lock.acquire()
    pid = os.fork()
    if pid == 0:
        try:
            assert asr._cached_transcriptor is None
            asr._obtener_transcriptor()
            os.write(write_fd, b"ok")
        finally:
            os._exit(0)
    asr._lock.release()
    os.close(write_fd)
    try:
        ready, _, _ = select.select([read_fd], [], [], 5)
        assert ready, "El hijo heredo un bloqueo adquirido"
        assert os.read(read_fd, 2) == b"ok"
    finally:
        os.close(read_fd)
        if not ready:
            import signal

            os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)


def test_transcribe_conserva_parametros_y_texto(model_settings, monkeypatch):
    import sys
    from types import SimpleNamespace

    model = Mock()
    model.transcribe.return_value = (
        iter([SimpleNamespace(start=0, end=30, text="  texto  ")]),
        None,
    )
    monkeypatch.setitem(
        sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Mock(return_value=model))
    )
    transcriptor = asr.TranscriptorFasterWhisper(model_settings, device="cpu", compute_type="int8")
    assert list(transcriptor.transcribe(model_settings / "audio.wav")) == [(0, 30, "  texto  ")]
    model.transcribe.assert_called_once_with(str(model_settings / "audio.wav"), language="es")
    monkeypatch.setattr(asr.os, "getpid", lambda: -1)
    with pytest.raises(Exception):
        list(transcriptor.transcribe(model_settings / "audio.wav"))
    assert model.transcribe.call_count == 1


@pytest.mark.parametrize(
    "setting,value",
    [
        ("HOMEX_ASR_DEVICE", "cuda"),
        ("HOMEX_ASR_COMPUTE_TYPE", "float32"),
    ],
)
def test_clave_configuracion_completa(model_settings, monkeypatch, setting, value):
    constructor = Mock()
    monkeypatch.setattr(asr, "TranscriptorFasterWhisper", constructor)
    asr._obtener_transcriptor()
    with override_settings(**{setting: value}):
        asr._obtener_transcriptor()
    assert constructor.call_count == 2


def test_cambio_ruta(model_settings, monkeypatch, tmp_path):
    constructor = Mock()
    monkeypatch.setattr(asr, "TranscriptorFasterWhisper", constructor)
    asr._obtener_transcriptor()
    otra = tmp_path / "otro-modelo"
    otra.mkdir()
    with override_settings(HOMEX_ASR_MODEL_PATH=str(otra)):
        asr._obtener_transcriptor()
    assert constructor.call_count == 2


def test_error_constructor_tiene_codigo_seguro(model_settings, monkeypatch):
    import sys
    from types import SimpleNamespace

    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        SimpleNamespace(WhisperModel=Mock(side_effect=RuntimeError("ruta y datos privados"))),
    )
    with pytest.raises(asr.HomexError) as error:
        asr._obtener_transcriptor()
    assert error.value.detail.code == "MODEL_UNAVAILABLE"
    assert "datos privados" not in str(error.value)
    assert asr._cached_transcriptor is None


@pytest.fixture(autouse=True)
def catalogo_estructural():
    """Estas pruebas de ciclo de vida no usan conexiones DB heredables por fork."""


@pytest.fixture(autouse=True)
def transiciones_pedido():
    pass


def test_servicio_no_confunde_duracion_audio_con_timestamps(tmp_path):
    import wave

    from homex_nlp.asr import AsrService
    from homex_nlp.contracts import TranscriptionResult

    audio = tmp_path / "test.wav"
    with wave.open(str(audio), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * 16000)
    transcriber = Mock(model_version="test")
    transcriber.transcribe.return_value = [(0, 2, "texto completo")]
    result = AsrService(transcriber).transcribe(audio)
    assert result.text_original == "texto completo"
    assert result.duration_seconds is None
    assert result.segments[0].end_seconds == "2.000000"
    assert not audio.exists()
    assert TranscriptionResult.model_validate(result.model_dump()) == result


def test_inferencia_serializa_iterador_diferido(model_settings, monkeypatch):
    import sys
    import time
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock
    from types import SimpleNamespace

    active = 0
    peak = 0
    counter_lock = Lock()

    def segments():
        nonlocal active, peak
        with counter_lock:
            active += 1
            peak = max(peak, active)
        try:
            time.sleep(0.02)
            yield SimpleNamespace(start=0, end=1, text="test")
        finally:
            with counter_lock:
                active -= 1

    model = Mock()
    model.transcribe.side_effect = lambda *args, **kwargs: (segments(), None)
    monkeypatch.setitem(
        sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Mock(return_value=model))
    )
    transcriber = asr.TranscriptorFasterWhisper(model_settings, device="cpu", compute_type="int8")
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: list(transcriber.transcribe(model_settings / "a.wav")), range(4)))
    assert peak == 1
    assert active == 0
