from __future__ import annotations

import logging
import os
from pathlib import Path
from threading import Lock
from time import perf_counter

from django.conf import settings
from homex_nlp.asr import AsrService
from homex_nlp.contracts.error import ErrorDetail
from homex_nlp.errors import HomexError

logger = logging.getLogger(__name__)

# Cache local al proceso: nunca compartir objetos de CTranslate2 entre forks.
# La vida del modelo es la del worker; un despliegue de pesos requiere reiniciar workers.
_lock = Lock()
_cached_pid: int | None = None
_cached_config: tuple[str, str, str] | None = None
_cached_transcriptor: TranscriptorFasterWhisper | None = None


def _reset_after_fork() -> None:
    global _lock, _cached_pid, _cached_config, _cached_transcriptor
    _lock = Lock()
    _cached_pid = None
    _cached_config = None
    _cached_transcriptor = None


os.register_at_fork(after_in_child=_reset_after_fork)


class TranscriptorFasterWhisper:
    def __init__(self, model_path: Path, *, device: str, compute_type: str) -> None:
        if not model_path.is_dir():
            raise HomexError(
                ErrorDetail(
                    code="MODEL_UNAVAILABLE",
                    message="El modelo ASR local no está disponible.",
                    retryable=True,
                )
            )
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise HomexError(
                ErrorDetail(
                    code="MODEL_UNAVAILABLE",
                    message="El worker requiere el extra worker.",
                    retryable=True,
                )
            ) from exc
        self.model_version = model_path.name
        self._model_path = model_path
        self._pid = os.getpid()
        self._inference_lock = Lock()
        try:
            self._model = WhisperModel(str(model_path), device=device, compute_type=compute_type)
        except Exception as exc:
            raise HomexError(
                ErrorDetail(
                    code="MODEL_UNAVAILABLE",
                    message="El modelo ASR local no pudo cargarse.",
                    retryable=True,
                )
            ) from exc

    def transcribe(self, path: Path):
        if self._pid != os.getpid() or not self._model_path.is_dir():
            raise HomexError(
                ErrorDetail(
                    code="MODEL_UNAVAILABLE",
                    message="El modelo ASR no está disponible en este proceso.",
                    retryable=True,
                )
            )
        # El iterador ejecuta la inferencia de forma diferida: mantener el lock hasta agotarlo.
        with self._inference_lock:
            segmentos, _ = self._model.transcribe(str(path), language="es")
            for segmento in segmentos:
                yield segmento.start, segmento.end, segmento.text


def _obtener_transcriptor() -> TranscriptorFasterWhisper:
    global _cached_pid, _cached_config, _cached_transcriptor

    started = perf_counter()
    pid = os.getpid()
    configured_path = settings.HOMEX_ASR_MODEL_PATH
    if not configured_path:
        with _lock:
            _cached_transcriptor = None
            _cached_config = None
        raise HomexError(
            ErrorDetail(
                code="MODEL_UNAVAILABLE",
                message="El modelo ASR local no está disponible.",
                retryable=True,
            )
        )
    path = Path(configured_path).resolve()
    config = (str(path), str(settings.HOMEX_ASR_DEVICE), str(settings.HOMEX_ASR_COMPUTE_TYPE))

    # Lock por proceso: evita doble inicialización ante llamadas desde hilos.
    with _lock:
        if _cached_pid == pid and _cached_config == config and _cached_transcriptor is not None:
            if not path.is_dir():
                _cached_transcriptor = None
                _cached_config = None
                raise HomexError(
                    ErrorDetail(
                        code="MODEL_UNAVAILABLE",
                        message="El modelo ASR local no está disponible.",
                        retryable=True,
                    )
                )
            return _cached_transcriptor

        # No servir un objeto heredado de otro PID ni de otra configuración.
        _cached_transcriptor = None
        _cached_config = None
        _cached_pid = pid
        try:
            nuevo = TranscriptorFasterWhisper(path, device=config[1], compute_type=config[2])
        except Exception:
            # Una carga fallida nunca se reutiliza; siguiente intento puede reintentar.
            logger.warning("Carga del modelo ASR no completada; siguiente llamada reintentará.")
            raise
        _cached_transcriptor = nuevo
        _cached_config = config
        logger.info(
            "Modelo ASR inicializado para el worker; duracion_carga_ms=%d",
            int((perf_counter() - started) * 1000),
        )
        return nuevo


def construir_servicio_asr() -> AsrService:
    return AsrService(_obtener_transcriptor(), max_bytes=settings.HOMEX_AUDIO_MAX_BYTES)
