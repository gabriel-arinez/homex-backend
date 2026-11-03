"""Catalog draft capture: evidence only, no product or inventory writes."""

import json
import re
from hashlib import sha256

from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from homex_nlp.catalog import CatalogRequest, CatalogValue, extract_catalog
from rest_framework.exceptions import NotFound, ValidationError

from apps.capturas.audio import guardar_audio, hash_audio
from apps.capturas.models import Captura
from apps.capturas.services import ConflictoIdempotencia, RecepcionCaptura, crear_intento
from apps.catalogo.models import ValorCatalogo

MODO = "CATALOGO_CREACION"


@transaction.atomic
def recibir_catalogo(
    *,
    actor,
    clave_idempotencia,
    sesion_borrador,
    categoria,
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
    if not ValorCatalogo.objects.filter(
        concepto__codigo="CATEGORIA_PRODUCTO", concepto__activo=True, codigo=categoria, activo=True
    ).exists():
        raise ValidationError({"categoria": "Categoría inexistente o inactiva."})
    proforma, moneda, contexto = None, "BOB", None
    if captura_origen is not None:
        origen = Captura.objects.filter(
            pk=captura_origen, vendedor=actor, modo_captura=MODO, sesion_borrador=sesion_borrador
        ).first()
        if origen is None:
            raise NotFound()
        if origen.categoria_catalogo != categoria:
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
                "categoria": categoria,
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
            and captura.categoria_catalogo == categoria
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
        sesiones.exclude(vendedor=actor, categoria_catalogo=categoria).exists()
        or sesiones.filter(proforma__isnull=False).exclude(proforma=contexto).exists()
    ):
        raise ValidationError({"sesion_borrador": "La sesión pertenece a otro contexto."})
    try:
        with transaction.atomic():
            captura = Captura.objects.create(
                modo_captura=MODO,
                categoria_catalogo=categoria,
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


def propuesta_catalogo(captura, texto):
    values = [
        CatalogValue(id=v.id, concept=v.concepto.codigo, code=v.codigo, name=v.nombre)
        for v in ValorCatalogo.objects.select_related("concepto").filter(
            activo=True, concepto__activo=True
        )
    ]
    result = extract_catalog(
        CatalogRequest(category=captura.categoria_catalogo, text=texto, values=values)
    ).model_dump(mode="json")
    # Validate each suggestion with the same field types and catalog rules as manual creation.
    from apps.catalogo.api.serializers import ProductoSerializer

    fields = result["fields"]
    if "precio_lista" in fields and re.search(r"\b(?:USD|EUR|d[oó]lares?|euros?)\b", texto, re.I):
        fields.pop("precio_lista")
        result["warnings"].append(
            "El precio de lista requiere BOB; no se convierten monedas por voz."
        )
    nested = "silla" if captura.categoria_catalogo == "SILLA" else "piso"
    general = {"nombre", "observaciones", "precio_lista", "unidad_stock"}
    unit = fields.get("unidad_stock")
    allowed = {"SILLA": {"PIEZA"}, "PISO_FLOTANTE": {"M2"}, "OTRO": {"PIEZA", "JUEGO", "BARRA"}}[
        captura.categoria_catalogo
    ]
    if unit and not any(v.id == unit and v.code in allowed for v in values):
        fields.pop("unidad_stock")
        result["warnings"].append("Unidad comercial incompatible con la categoría.")
    for key, value in list(fields.items()):
        serializer = ProductoSerializer(
            data={key: value} if key in general else {nested: {key: value}}, partial=True
        )
        # Run the real individual DRF field; object validation also requires mandatory fields.
        try:
            field = (
                serializer.fields[key] if key in general else serializer.fields[nested].fields[key]
            )
            field.run_validation(value)
        except (ValidationError, KeyError, TypeError, ValueError):
            fields.pop(key)
            result["warnings"].append(f"{key}: valor incompatible con el formulario.")
    # Backend rejection must also invalidate the associated evidence.
    for evidence in result["evidence"]:
        root = evidence["label"].split(".")[0]
        if evidence["decision"] == "ACCEPTED" and root not in fields:
            evidence["decision"] = "UNRESOLVED"
            evidence["reason"] = "Valor descartado por validación del formulario."
    return result


def resultado_catalogo(captura):
    intento = captura.intentocaptura_set.order_by("-numero_intento").first()
    return {
        "id": captura.id,
        "estado": captura.estado,
        "categoria": captura.categoria_catalogo,
        "texto_transcrito_original": captura.texto_transcrito,
        "propuesta": intento.resultado_raw if intento else None,
        "error_codigo": intento.error_codigo if intento else None,
    }
