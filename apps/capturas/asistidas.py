"""Recepción y vinculación diferida de captura asistida sobre el outbox existente."""

import json
from copy import deepcopy
from hashlib import sha256

from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.capturas.audio import guardar_audio, hash_audio
from apps.capturas.models import Captura, RevisionAsistida
from apps.capturas.proyeccion_prf03 import VERSION_PROYECCION
from apps.capturas.services import ConflictoIdempotencia, RecepcionCaptura, crear_intento
from apps.proformas.models import EspecificacionMueble, Proforma

MODO = "ASISTIDA_CREACION_MUEBLE"


def _contexto(*, actor, proforma_id, moneda_codigo):
    if proforma_id is None:
        if moneda_codigo not in {"BOB", "USD"}:
            raise ValidationError({"moneda_codigo": "Indique BOB o USD."})
        return None, moneda_codigo
    try:
        proforma = (
            Proforma.objects.select_for_update()
            .select_related("estado", "moneda")
            .get(pk=proforma_id)
        )
    except Proforma.DoesNotExist as exc:
        raise NotFound() from exc
    if proforma.vendedor_id != actor.id and not (actor.is_staff or actor.is_superuser):
        raise PermissionDenied()
    if proforma.estado.codigo not in {"BORRADOR", "EN_REVISION"}:
        raise ValidationError({"proforma": "La proforma no es editable."})
    if moneda_codigo and moneda_codigo != proforma.moneda.codigo:
        raise ValidationError({"moneda_codigo": "La moneda no coincide con la proforma."})
    return proforma, proforma.moneda.codigo


@transaction.atomic
def recibir_asistida(
    *,
    actor,
    clave_idempotencia,
    sesion_borrador,
    proforma=None,
    moneda_codigo=None,
    captura_origen=None,
    texto=None,
    audio=None,
):
    if (texto is None) == (audio is None):
        raise ValidationError("Envíe exactamente uno de texto o audio.")
    # Serializa la primera vinculación de una sesión sin depender de una fila aún inexistente.
    session_lock = int.from_bytes(
        sha256(str(sesion_borrador).encode()).digest()[:8], "big", signed=True
    )
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [session_lock])
    contexto, moneda = _contexto(actor=actor, proforma_id=proforma, moneda_codigo=moneda_codigo)
    if captura_origen is not None:
        origen = Captura.objects.filter(
            pk=captura_origen, vendedor=actor, modo_captura=MODO, sesion_borrador=sesion_borrador
        ).first()
        if origen is None:
            raise NotFound()
        if origen.moneda_contexto_codigo != moneda or origen.proforma_id != proforma:
            raise ValidationError({"captura_origen": "El contexto de origen no coincide."})
    entrada = hash_audio(audio) if audio is not None else sha256(texto.encode()).hexdigest()
    input_hash = sha256(
        f"{'audio' if audio is not None else 'texto'}:{entrada}".encode()
    ).hexdigest()

    input_hash = sha256(
        json.dumps(
            {
                "entrada": input_hash,
                "actor": actor.id,
                "sesion": str(sesion_borrador),
                "proforma_original": proforma,
                "moneda": moneda,
                "origen": captura_origen,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()

    def repeticion(captura):
        intento = captura.intentocaptura_set.order_by("numero_intento").first()
        if not (
            captura.vendedor_id == actor.id
            and captura.modo_captura == MODO
            and captura.sesion_borrador == sesion_borrador
            and (
                captura.proforma_id == proforma
                or proforma is None
                and captura.proforma_detalle_id is not None
            )
            and captura.moneda_contexto_codigo == moneda
            and captura.captura_origen_id == captura_origen
            and intento
            and intento.input_hash == input_hash
        ):
            raise ConflictoIdempotencia()
        return RecepcionCaptura(captura, intento, True)

    existente = (
        Captura.objects.select_for_update().filter(clave_idempotencia=clave_idempotencia).first()
    )
    if existente:
        return repeticion(existente)
    # Una sesión se mantiene ligada a un actor y un contexto, incluso antes del primer guardado.
    sesiones = Captura.objects.filter(modo_captura=MODO, sesion_borrador=sesion_borrador)
    if (
        sesiones.exclude(vendedor=actor, moneda_contexto_codigo=moneda).exists()
        or sesiones.filter(proforma__isnull=False).exclude(proforma=contexto).exists()
    ):
        raise ValidationError({"sesion_borrador": "La sesión pertenece a otro contexto."})
    try:
        with transaction.atomic():
            captura = Captura.objects.create(
                modo_captura=MODO,
                sesion_borrador=sesion_borrador,
                moneda_contexto_codigo=moneda,
                captura_origen_id=captura_origen,
                proforma=contexto,
                vendedor=actor,
                clave_idempotencia=clave_idempotencia,
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
        return repeticion(existente)
    intento = crear_intento(captura_id=captura.id, input_hash=input_hash)
    if audio is not None:
        guardar_audio(intento_id=intento.id, archivo=audio)
    return RecepcionCaptura(captura, intento, False)


def resultado_asistida(captura):
    intento = captura.intentocaptura_set.order_by("-numero_intento").first()
    raw = intento.resultado_raw or {} if intento else {}
    propuesta = intento.proyeccion_configurador if intento else None
    resultado = (
        "ERROR" if intento and intento.estado == "ERROR" else raw.get("status", "PROCESSING")
    )
    return {
        "id": captura.id,
        "estado": captura.estado,
        "intento_id": intento.id if intento else None,
        "texto_transcrito_original": captura.texto_transcrito,
        "resultado": resultado,
        "propuesta_configurador": deepcopy(propuesta),
        "pendientes": propuesta["pendientes"] if propuesta else [],
        "version_proyeccion": propuesta.get("version_proyeccion", VERSION_PROYECCION)
        if propuesta
        else VERSION_PROYECCION,
        "motor": raw.get("engine"),
        "error_codigo": intento.error_codigo if intento and intento.estado == "ERROR" else None,
    }


def _hojas(valor, ruta=""):
    if isinstance(valor, dict):
        return {p: v for k, item in valor.items() for p, v in _hojas(item, f"{ruta}/{k}").items()}
    if isinstance(valor, list):
        return {
            p: v for i, item in enumerate(valor) for p, v in _hojas(item, f"{ruta}/{i}").items()
        }
    return {} if valor is None or valor == "" else {ruta: valor}


def vincular_asistida(*, captura_id, detalle, actor, sesion_borrador):
    """El llamador mantiene la transacción y el lock de proforma PRF-03."""
    captura = (
        Captura.objects.select_for_update()
        .filter(pk=captura_id, vendedor=actor, modo_captura=MODO)
        .first()
    )
    if captura is None:
        raise ValidationError({"captura_asistida_id": "Captura no disponible para este actor."})
    if (
        not sesion_borrador
        or captura.sesion_borrador != sesion_borrador
        or captura.proforma_id not in {None, detalle.proforma_id}
        or captura.moneda_contexto_codigo != detalle.proforma.moneda.codigo
        or captura.proforma_detalle_id is not None
    ):
        raise ConflictoIdempotencia("Captura ya utilizada o contexto incompatible.")
    ficha = EspecificacionMueble.objects.filter(proforma_detalle=detalle).first()
    if detalle.tipo_item.codigo != "MUEBLE_MEDIDA" or ficha is None:
        raise ValidationError(
            {"captura_asistida_id": "Requiere una nueva línea y ficha de mueble."}
        )
    intento = captura.intentocaptura_set.select_for_update().order_by("-numero_intento").first()
    if (
        captura.estado != "COMPLETADA"
        or not intento
        or intento.estado != "FINALIZADO"
        or not intento.proyeccion_configurador
        or (intento.resultado_raw or {}).get("status") != "REQUIRES_REVIEW"
    ):
        raise ValidationError({"captura_asistida_id": "La captura no tiene propuesta utilizable."})
    humano = {
        "comercial": {
            "nombre": detalle.nombre,
            "cantidad": int(detalle.cantidad),
            "unidad_codigo": detalle.unidad.codigo,
            "precio_unitario": str(detalle.precio_unitario),
            "descuento": str(detalle.descuento),
        },
        "especificacion": {
            "tipo_mueble": ficha.tipo_mueble_id,
            "datos_tecnicos": ficha.datos_tecnicos,
            "observaciones": ficha.observaciones,
        },
    }
    original = deepcopy(intento.proyeccion_configurador)
    original.pop("pendientes", None)
    original.pop("version_proyeccion", None)
    a, b = _hojas(original), _hojas(humano)
    comunes = a.keys() & b.keys()
    comparacion = {
        "campos_totales": len(a),
        "tiempo_hasta_incorporacion_ms": max(
            0, int((timezone.now() - captura.capturado_at).total_seconds() * 1000)
        ),
        "corregidos": sorted(p for p in comunes if a[p] != b[p]),
        "agregados": sorted(b.keys() - a.keys()),
        "eliminados": sorted(a.keys() - b.keys()),
    }
    RevisionAsistida.objects.create(
        captura=captura,
        intento=intento,
        detalle=detalle,
        propuesta_original=original,
        resultado_humano=humano,
        comparacion=comparacion,
        revisor=actor,
        revisado_at=timezone.now(),
    )
    captura.proforma = detalle.proforma
    captura.proforma_detalle = detalle
    captura.save(update_fields=["proforma", "proforma_detalle"])
