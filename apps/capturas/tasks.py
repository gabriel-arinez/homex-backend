from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.capturas.audio import directorio_audio
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


@shared_task(name="capturas.limpiar_audio_temporal")
def limpiar_audio_temporal_task() -> int:
    umbral = timezone.now() - timedelta(seconds=settings.HOMEX_AUDIO_TTL_SECONDS)
    eliminados = 0
    for ruta in directorio_audio().iterdir():
        if ruta.is_file() and not ruta.is_symlink() and ruta.stat().st_mtime < umbral.timestamp():
            ruta.unlink(missing_ok=True)
            eliminados += 1
    return eliminados
