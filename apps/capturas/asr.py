from __future__ import annotations

from pathlib import Path

from django.conf import settings
from homex_nlp.asr import AsrService
from homex_nlp.contracts.error import ErrorDetail
from homex_nlp.errors import HomexError


class TranscriptorFasterWhisper:
    def __init__(self) -> None:
        model_path = settings.HOMEX_ASR_MODEL_PATH
        if not model_path or not Path(model_path).is_dir():
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
        self.model_version = Path(model_path).name
        self._model = WhisperModel(
            model_path,
            device=settings.HOMEX_ASR_DEVICE,
            compute_type=settings.HOMEX_ASR_COMPUTE_TYPE,
        )

    def transcribe(self, path: Path):
        segmentos, _ = self._model.transcribe(str(path), language="es")
        for segmento in segmentos:
            yield segmento.start, segmento.end, segmento.text


def construir_servicio_asr() -> AsrService:
    return AsrService(TranscriptorFasterWhisper(), max_bytes=settings.HOMEX_AUDIO_MAX_BYTES)
