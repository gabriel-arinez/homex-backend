from __future__ import annotations

import os
import shutil
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile

SUFIJOS_AUDIO = {".wav", ".mp3", ".m4a", ".ogg", ".webm"}


class AudioTemporalInvalido(ValueError):
    pass


def validar_duracion_audio(ruta: Path, *, max_seconds: int) -> None:
    """Rechaza audio demasiado largo decodificando todos los fotogramas de audio.

    PyAV viene incluido en el extra worker (faster-whisper). No confiar en metadatos
    de duración que puedan estar ausentes o manipulados por el cliente.
    """
    try:
        import av
    except ImportError as exc:
        raise AudioTemporalInvalido("No está disponible el decodificador de audio.") from exc

    try:
        segundos = 0.0
        hay_audio = False
        with av.open(str(ruta)) as container:
            streams = [stream for stream in container.streams if stream.type == "audio"]
            if not streams:
                raise AudioTemporalInvalido("El archivo no contiene audio.")
            for frame in container.decode(audio=streams[0].index):
                hay_audio = True
                if not frame.sample_rate or frame.sample_rate <= 0:
                    raise AudioTemporalInvalido("El audio contiene una frecuencia inválida.")
                segundos += frame.samples / frame.sample_rate
                if segundos > max_seconds:
                    raise AudioTemporalInvalido(
                        f"El audio supera los {max_seconds // 60} minutos permitidos."
                    )
        if not hay_audio:
            raise AudioTemporalInvalido("El archivo no contiene audio decodificable.")
    except AudioTemporalInvalido:
        raise
    except Exception as exc:
        raise AudioTemporalInvalido("No se pudo validar la duración del audio.") from exc


def directorio_audio() -> Path:
    root = Path(settings.HOMEX_AUDIO_TEMP_ROOT)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    return root.resolve()


def hash_audio(archivo: UploadedFile) -> str:
    digest = sha256()
    total = 0
    for chunk in archivo.chunks():
        total += len(chunk)
        if total > settings.HOMEX_AUDIO_MAX_BYTES:
            raise AudioTemporalInvalido("El audio supera el límite permitido.")
        digest.update(chunk)
    archivo.seek(0)
    if total == 0:
        raise AudioTemporalInvalido("El audio está vacío.")
    return digest.hexdigest()


def guardar_audio(*, intento_id: int, archivo: UploadedFile) -> Path:
    sufijo = Path(archivo.name).suffix.lower()
    if sufijo not in SUFIJOS_AUDIO:
        raise AudioTemporalInvalido("Formato de audio no admitido.")
    root = directorio_audio()
    destino = root / f"intento-{intento_id}{sufijo}"
    temporal = root / f".{destino.name}.part"
    descriptor = os.open(temporal, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as salida:
            for chunk in archivo.chunks():
                salida.write(chunk)
        temporal.replace(destino)
        return destino
    except Exception:
        temporal.unlink(missing_ok=True)
        destino.unlink(missing_ok=True)
        raise


def ruta_audio(intento_id: int) -> Path | None:
    coincidencias = list(directorio_audio().glob(f"intento-{intento_id}.*"))
    seguras = [ruta for ruta in coincidencias if ruta.is_file() and not ruta.is_symlink()]
    return seguras[0] if len(seguras) == 1 else None


def eliminar_audio(intento_id: int) -> None:
    root = directorio_audio()
    for ruta in root.glob(f"intento-{intento_id}.*"):
        if ruta.is_file() and not ruta.is_symlink():
            ruta.unlink(missing_ok=True)


def copiar_audio_para_asr(intento_id: int) -> Path:
    """Crea una copia descartable para ASR sin entregar el original al consumidor."""
    origen = ruta_audio(intento_id)
    if origen is None:
        raise AudioTemporalInvalido("Audio temporal no disponible.")

    root = directorio_audio()
    destino = root / f".asr-intento-{intento_id}-{uuid4().hex}{origen.suffix.lower()}"
    descriptor = os.open(destino, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with origen.open("rb") as entrada, os.fdopen(descriptor, "wb") as salida:
            shutil.copyfileobj(entrada, salida)
        return destino
    except Exception:
        destino.unlink(missing_ok=True)
        raise
