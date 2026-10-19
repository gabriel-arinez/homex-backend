import hashlib
import re
import unicodedata
from difflib import SequenceMatcher

from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from apps.catalogo.models import ConceptoCatalogo, ValorCatalogo
from apps.core.exceptions import ConflictoComercial

MAX_CONJUNTOS = 10
MAX_COMPONENTES = 40


def normalizar(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto.casefold())
    base = "".join(c for c in base if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", base).split())


def sanitizar_nombre(nombre):
    if not isinstance(nombre, str):
        raise ValidationError({"nombre": "Debe ser texto."})
    nombre = " ".join(nombre.split())
    if not nombre or len(nombre) > 150 or any(unicodedata.category(c) == "Cc" for c in nombre):
        raise ValidationError({"nombre": "Ingrese un nombre válido de hasta 150 caracteres."})
    return nombre


def _codigo(nombre, concepto):
    normalizado = normalizar(nombre)
    base = normalizado.replace(" ", "_").upper()[:80] or "TIPO_MUEBLE"
    if not ValorCatalogo.objects.filter(concepto=concepto, codigo=base).exists():
        return base
    sufijo = hashlib.sha256(normalizado.encode()).hexdigest()[:8].upper()
    return f"{base[:71]}_{sufijo}"


def _existente_normalizado(concepto, nombre):
    objetivo = normalizar(nombre)
    return next(
        (
            valor
            for valor in ValorCatalogo.objects.filter(concepto=concepto)
            if normalizar(valor.nombre) == objetivo
        ),
        None,
    )


@transaction.atomic
def crear_tipo_mueble(*, nombre, actor):
    nombre = sanitizar_nombre(nombre)
    concepto = ConceptoCatalogo.objects.select_for_update().get(codigo="TIPO_MUEBLE", activo=True)
    existente = _existente_normalizado(concepto, nombre)
    if existente:
        raise ConflictoComercial({"codigo": "tipo_duplicado", "existente": resumen_tipo(existente)})
    try:
        with transaction.atomic():
            return ValorCatalogo.objects.create(
                concepto=concepto,
                codigo=_codigo(nombre, concepto),
                nombre=nombre,
                activo=True,
                created_by=actor,
                updated_by=actor,
            )
    except IntegrityError:
        existente = _existente_normalizado(concepto, nombre)
        if existente:
            raise ConflictoComercial(
                {"codigo": "tipo_duplicado", "existente": resumen_tipo(existente)}
            ) from None
        raise


def resumen_tipo(valor):
    return {"id": valor.id, "codigo": valor.codigo, "nombre": valor.nombre}


def tipos_similares(nombre, *, limite=5):
    objetivo = normalizar(nombre)
    if not objetivo:
        return []
    candidatos = ValorCatalogo.objects.filter(concepto__codigo="TIPO_MUEBLE", activo=True)
    puntuados = [
        (SequenceMatcher(None, objetivo, normalizar(v.nombre)).ratio(), v) for v in candidatos
    ]
    return [resumen_tipo(v) for score, v in sorted(puntuados, reverse=True) if score >= 0.62][
        :limite
    ]
