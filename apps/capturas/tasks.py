from __future__ import annotations

import re
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.capturas.audio import directorio_audio
from apps.capturas.models import IntentoCaptura
from apps.capturas.outbox import publicar_pendientes, reconciliar_publicados
from apps.capturas.pipeline import procesar_intento


@shared_task(
    name="capturas.procesar_intento", bind=True, acks_late=True, reject_on_worker_lost=True
)
def procesar_intento_task(self, intento_id: int, clave_unica: str):
    del self, clave_unica
    return procesar_intento(intento_id=intento_id)


@shared_task(name="capturas.publicar_outbox")
def publicar_outbox_task():
    return publicar_pendientes()


@shared_task(name="capturas.reconciliar_outbox")
def reconciliar_outbox_task():
    return reconciliar_publicados()


_AUDIO_ORIGINAL_RE = re.compile(r"^intento-(?P<intento_id>\\d+)\\.[^.]+$")


def _audio_vencido_es_eliminable(ruta) -> bool:
    """No elimina el único audio capaz de recuperar trabajo aún pendiente."""
    if ruta.name.startswith(".asr-intento-"):
        return True

    coincidencia = _AUDIO_ORIGINAL_RE.match(ruta.name)
    if coincidencia is None:
        return True

    intento = (
        IntentoCaptura.objects.select_related("captura")
        .filter(pk=int(coincidencia.group("intento_id")))
        .first()
    )
    if intento is None:
        return True

    if intento.captura.texto_transcrito:
        return True

    return intento.estado in {"FINALIZADO", "ERROR"}


@shared_task(name="capturas.limpiar_audio_temporal")
def limpiar_audio_temporal_task() -> int:
    umbral = timezone.now() - timedelta(seconds=settings.HOMEX_AUDIO_TTL_SECONDS)
    eliminados = 0
    for ruta in directorio_audio().iterdir():
        if not ruta.is_file() or ruta.is_symlink():
            continue
        if ruta.stat().st_mtime >= umbral.timestamp():
            continue
        if not _audio_vencido_es_eliminable(ruta):
            continue
        ruta.unlink(missing_ok=True)
        eliminados += 1
    return eliminados
