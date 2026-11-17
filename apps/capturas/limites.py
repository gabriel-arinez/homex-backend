"""Shared capture transcript boundary, aligned with the installed NLP contract."""

LIMITE_TEXTO_CAPTURA = 20_000


def validar_texto_captura(texto):
    """Require textual content, not commercial sufficiency (which belongs to NLP)."""
    from rest_framework.exceptions import ValidationError

    if len(texto) > LIMITE_TEXTO_CAPTURA:
        raise ValidationError({"texto": "La transcripción supera los 20000 caracteres."})
    if not any(character.isalpha() for character in texto):
        raise ValidationError({"texto": "Ingrese contenido textual procesable."})


LIMITE_TEXTO_COMERCIAL = 3000
MIN_PALABRAS_COMERCIAL = 20


def contar_palabras_comerciales(texto):
    """Count whitespace-delimited tokens containing a Unicode letter or number."""
    return sum(any(char.isalnum() for char in token) for token in texto.split())


def validar_texto_comercial(texto):
    """Apply operational thresholds only to the commercial voice assistant."""
    from rest_framework.exceptions import ValidationError

    if len(texto) > LIMITE_TEXTO_COMERCIAL:
        raise ValidationError(
            {"texto": "La transcripción supera los 3000 caracteres. Reduzca el texto."}
        )
    if contar_palabras_comerciales(texto) < MIN_PALABRAS_COMERCIAL:
        raise ValidationError({"texto": "Complete la descripción con al menos 20 palabras."})


def auditoria_transcripcion(captura, intento):
    raw = (intento.resultado_raw or {}) if intento else {}
    origen = origen_canonico(captura.captura_origen) if captura.captura_origen_id else None
    fuente = origen or captura
    intento_fuente = (
        fuente.intentocaptura_set.order_by("numero_intento").first() if origen else intento
    )
    tiene_asr = bool(
        intento_fuente
        and (
            intento_fuente.modelo_asr_version
            or (intento_fuente.resultado_raw or {}).get("solo_transcribir")
        )
    )
    return {
        "solo_transcribir": bool(raw.get("solo_transcribir")),
        "captura_origen": origen.pk if origen else None,
        "texto_asr_original": fuente.texto_transcrito if tiene_asr else None,
        "texto_corregido": captura.texto_transcrito if origen else None,
    }


def origen_canonico(captura, *, validar=None):
    """Resolve historical chains without mutating their immutable input rows."""
    from rest_framework.exceptions import NotFound, ValidationError

    seen = set()
    current = captura
    asr_origin = None
    while current is not None:
        if current.pk in seen:
            raise ValidationError({"captura_origen": "Cadena de origen inválida."})
        seen.add(current.pk)
        if any(
            getattr(current, field) != getattr(captura, field)
            for field in (
                "vendedor_id",
                "modo_captura",
                "sesion_borrador",
                "categoria_catalogo",
                "moneda_contexto_codigo",
                "proforma_id",
            )
        ):
            raise NotFound()
        if validar:
            validar(current)
        attempt = current.intentocaptura_set.order_by("numero_intento").first()
        if attempt and (
            attempt.modelo_asr_version or (attempt.resultado_raw or {}).get("solo_transcribir")
        ):
            asr_origin = current
        if current.captura_origen_id is None:
            break
        current = current.captura_origen
    return asr_origin or captura
