from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from apps.capturas.models import Captura, IntentoCaptura
from apps.proformas.models import Proforma


class ConflictoIdempotencia(APIException):
    status_code = 409
    default_code = "conflicto_idempotencia"
    default_detail = "La clave de idempotencia ya fue utilizada con otra solicitud."


@dataclass(frozen=True, slots=True)
class RecepcionCaptura:
    captura: Captura
    intento: IntentoCaptura
    reutilizada: bool


def _hash_texto(texto: str) -> str:
    return sha256(texto.encode("utf-8")).hexdigest()


def _validar_proforma(*, proforma: Proforma, actor, detalle_id: int | None) -> None:
    if proforma.vendedor_id != actor.id and not (actor.is_staff or actor.is_superuser):
        raise PermissionDenied("No puede registrar capturas para una proforma de otro vendedor.")
    if proforma.estado.codigo != "BORRADOR":
        raise ValidationError({"proforma": "Sólo una proforma BORRADOR admite capturas."})
    if detalle_id is not None and not proforma.detalles.filter(pk=detalle_id).exists():
        raise ValidationError({"proforma_detalle": "El detalle no pertenece a la proforma."})


def _validar_repeticion(
    *,
    captura: Captura,
    actor,
    proforma_id: int,
    detalle_id: int | None,
    input_hash: str,
) -> IntentoCaptura:
    intento = captura.intentocaptura_set.order_by("numero_intento").first()
    compatible = (
        captura.vendedor_id == actor.id
        and captura.proforma_id == proforma_id
        and captura.proforma_detalle_id == detalle_id
        and intento is not None
        and intento.input_hash == input_hash
    )
    if not compatible:
        raise ConflictoIdempotencia()
    return intento


@transaction.atomic
def recibir_captura_texto(
    *,
    actor,
    clave_idempotencia,
    proforma_id: int,
    texto: str,
    proforma_detalle_id: int | None = None,
) -> RecepcionCaptura:
    input_hash = _hash_texto(texto)
    existente = (
        Captura.objects.select_for_update().filter(clave_idempotencia=clave_idempotencia).first()
    )
    if existente is not None:
        intento = _validar_repeticion(
            captura=existente,
            actor=actor,
            proforma_id=proforma_id,
            detalle_id=proforma_detalle_id,
            input_hash=input_hash,
        )
        return RecepcionCaptura(existente, intento, True)

    try:
        proforma = Proforma.objects.select_for_update().select_related("estado").get(pk=proforma_id)
    except Proforma.DoesNotExist as exc:
        raise ValidationError({"proforma": "La proforma no existe."}) from exc
    _validar_proforma(proforma=proforma, actor=actor, detalle_id=proforma_detalle_id)

    try:
        with transaction.atomic():
            captura = Captura.objects.create(
                proforma=proforma,
                proforma_detalle_id=proforma_detalle_id,
                vendedor=actor,
                clave_idempotencia=clave_idempotencia,
                estado="PENDIENTE",
                capturado_at=timezone.now(),
                texto_transcrito=texto,
                created_by=actor,
                updated_by=actor,
            )
    except IntegrityError:
        existente = (
            Captura.objects.select_for_update()
            .filter(clave_idempotencia=clave_idempotencia)
            .first()
        )
        if existente is None:
            raise
        intento = _validar_repeticion(
            captura=existente,
            actor=actor,
            proforma_id=proforma_id,
            detalle_id=proforma_detalle_id,
            input_hash=input_hash,
        )
        return RecepcionCaptura(existente, intento, True)

    intento = crear_intento(captura_id=captura.id, input_hash=input_hash)
    return RecepcionCaptura(captura, intento, False)


@transaction.atomic
def crear_intento(*, captura_id: int, input_hash: str) -> IntentoCaptura:
    captura = Captura.objects.select_for_update().get(pk=captura_id)
    ultimo = (
        IntentoCaptura.objects.filter(captura=captura)
        .order_by("-numero_intento")
        .values_list("numero_intento", flat=True)
        .first()
        or 0
    )
    # El trigger DB-04 crea exactamente un TrabajoOutbox después de este INSERT.
    return IntentoCaptura.objects.create(
        captura=captura,
        numero_intento=ultimo + 1,
        estado="PENDIENTE",
        input_hash=input_hash,
        inicio_at=timezone.now(),
    )


@transaction.atomic
def recibir_captura_audio(
    *,
    actor,
    clave_idempotencia,
    proforma_id: int,
    archivo,
    proforma_detalle_id: int | None = None,
) -> RecepcionCaptura:
    from apps.capturas.audio import guardar_audio, hash_audio

    input_hash = hash_audio(archivo)
    existente = (
        Captura.objects.select_for_update().filter(clave_idempotencia=clave_idempotencia).first()
    )
    if existente is not None:
        intento = _validar_repeticion(
            captura=existente,
            actor=actor,
            proforma_id=proforma_id,
            detalle_id=proforma_detalle_id,
            input_hash=input_hash,
        )
        return RecepcionCaptura(existente, intento, True)

    try:
        proforma = Proforma.objects.select_for_update().select_related("estado").get(pk=proforma_id)
    except Proforma.DoesNotExist as exc:
        raise ValidationError({"proforma": "La proforma no existe."}) from exc
    _validar_proforma(proforma=proforma, actor=actor, detalle_id=proforma_detalle_id)

    try:
        with transaction.atomic():
            captura = Captura.objects.create(
                proforma=proforma,
                proforma_detalle_id=proforma_detalle_id,
                vendedor=actor,
                clave_idempotencia=clave_idempotencia,
                estado="PENDIENTE",
                capturado_at=timezone.now(),
                created_by=actor,
                updated_by=actor,
            )
    except IntegrityError:
        existente = (
            Captura.objects.select_for_update()
            .filter(clave_idempotencia=clave_idempotencia)
            .first()
        )
        if existente is None:
            raise
        intento = _validar_repeticion(
            captura=existente,
            actor=actor,
            proforma_id=proforma_id,
            detalle_id=proforma_detalle_id,
            input_hash=input_hash,
        )
        return RecepcionCaptura(existente, intento, True)

    intento = crear_intento(captura_id=captura.id, input_hash=input_hash)
    guardar_audio(intento_id=intento.id, archivo=archivo)
    return RecepcionCaptura(captura, intento, False)
