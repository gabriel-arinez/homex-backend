"""Shared capture transcript boundary, aligned with the installed NLP contract."""

LIMITE_TEXTO_CAPTURA = 20_000


def validar_texto_captura(texto):
    """Require textual content, not commercial sufficiency (which belongs to NLP)."""
    from rest_framework.exceptions import ValidationError

    if len(texto) > LIMITE_TEXTO_CAPTURA:
        raise ValidationError({"texto": "La transcripción supera los 20000 caracteres."})
    if not any(character.isalpha() for character in texto):
        raise ValidationError({"texto": "Ingrese contenido textual procesable."})


def auditoria_transcripcion(captura, intento):
    raw = (intento.resultado_raw or {}) if intento else {}
    origen = captura.captura_origen
    return {
        "solo_transcribir": bool(raw.get("solo_transcribir")),
        "captura_origen": captura.captura_origen_id,
        "texto_asr_original": origen.texto_transcrito if origen else captura.texto_transcrito,
        "texto_corregido": captura.texto_transcrito if origen else None,
    }
