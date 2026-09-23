from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.capturas.models import IntentoCaptura, TrabajoOutbox


def publicar_pendientes(*, limite: int = 100, enviar=None) -> dict[str, int]:
    if enviar is None:
        from apps.capturas.tasks import procesar_intento_task

        enviar = procesar_intento_task.apply_async
    publicados = errores = 0
    ids = list(
        TrabajoOutbox.objects.filter(publicado_at__isnull=True, disponible_at__lte=timezone.now())
        .order_by("id")
        .values_list("id", flat=True)[:limite]
    )
    for outbox_id in ids:
        with transaction.atomic():
            trabajo = (
                TrabajoOutbox.objects.select_for_update(skip_locked=True)
                .filter(pk=outbox_id, publicado_at__isnull=True)
                .first()
            )
            if trabajo is None:
                continue
            try:
                enviar(args=[trabajo.intento_id, trabajo.clave_unica], task_id=trabajo.clave_unica)
            except Exception as exc:
                trabajo.intentos_publicacion += 1
                trabajo.ultimo_error = type(exc).__name__
                trabajo.save(update_fields=["intentos_publicacion", "ultimo_error"])
                errores += 1
            else:
                trabajo.intentos_publicacion += 1
                trabajo.publicado_at = timezone.now()
                trabajo.ultimo_error = None
                trabajo.save(update_fields=["intentos_publicacion", "publicado_at", "ultimo_error"])
                publicados += 1
    return {"publicados": publicados, "errores": errores}


def reconciliar_publicados() -> int:
    umbral = timezone.now() - timedelta(seconds=settings.HOMEX_OUTBOX_RECONCILE_SECONDS)
    ids = list(
        TrabajoOutbox.objects.filter(
            publicado_at__lt=umbral,
            intento__estado__in=["PENDIENTE", "PROCESANDO"],
        ).values_list("id", flat=True)
    )
    reconciliados = 0
    for outbox_id in ids:
        with transaction.atomic():
            trabajo = (
                TrabajoOutbox.objects.select_for_update(skip_locked=True)
                .filter(
                    pk=outbox_id,
                    publicado_at__lt=umbral,
                    intento__estado__in=["PENDIENTE", "PROCESANDO"],
                )
                .first()
            )
            if trabajo is None:
                continue
            intento = IntentoCaptura.objects.select_for_update().get(pk=trabajo.intento_id)
            if intento.estado == "PROCESANDO":
                intento.estado = "PENDIENTE"
                intento.save(update_fields=["estado"])
            trabajo.publicado_at = None
            trabajo.disponible_at = timezone.now()
            trabajo.ultimo_error = "RECONCILIADO"
            trabajo.save(update_fields=["publicado_at", "disponible_at", "ultimo_error"])
            reconciliados += 1
    return reconciliados
