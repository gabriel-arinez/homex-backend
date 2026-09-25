"""Gate F08.4: PostgreSQL + Redis + worker Celery + wheel homex-nlp reales."""

from __future__ import annotations

import os
import sys
import time
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.integration")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from redis import Redis  # noqa: E402

from apps.capturas.models import ItemIA, TrabajoOutbox  # noqa: E402
from apps.capturas.outbox import publicar_pendientes  # noqa: E402
from apps.capturas.services import recibir_captura_texto  # noqa: E402
from apps.catalogo.models import ConceptoCatalogo, ValorCatalogo  # noqa: E402
from apps.proformas.services import crear_proforma  # noqa: E402

WHEEL = PROJECT_ROOT / "vendor" / "homex_nlp-0.1.0-py3-none-any.whl"
WHEEL_SHA256 = "cfacc3a987f6158f43934cb64304fa50ea3e577cfa576f3db1e6d2a9576d19e6"
TIEMPO_LIMITE_SEGUNDOS = 30


def valor(concepto_codigo: str, valor_codigo: str, nombre: str) -> ValorCatalogo:
    concepto, _ = ConceptoCatalogo.objects.get_or_create(codigo=concepto_codigo)
    resultado, _ = ValorCatalogo.objects.get_or_create(
        concepto=concepto,
        codigo=valor_codigo,
        defaults={"nombre": nombre},
    )
    return resultado


def verificar_runtime() -> None:
    if version("homex-nlp") != "0.1.0":
        raise AssertionError("El worker no utiliza homex-nlp 0.1.0.")
    if sha256(WHEEL.read_bytes()).hexdigest() != WHEEL_SHA256:
        raise AssertionError("El wheel homex-nlp no coincide con el hash fijado.")
    cliente_redis = Redis.from_url(settings.CELERY_BROKER_URL)
    if cliente_redis.ping() is not True:
        raise AssertionError("Redis no respondió PONG.")


def ejecutar() -> None:
    verificar_runtime()
    valor("ESTADO_PROFORMA", "BORRADOR", "Borrador")
    valor("MONEDA", "BOB", "Bolivianos")

    sufijo = uuid4().hex[:10]
    actor = get_user_model().objects.create_user(username=f"f084-{sufijo}")
    proforma = crear_proforma(actor=actor, prospecto_nombre="Integración F08.4")
    recepcion = recibir_captura_texto(
        actor=actor,
        clave_idempotencia=uuid4(),
        proforma_id=proforma.id,
        texto="Tres escritorios, total cien bolivianos",
    )

    trabajo = TrabajoOutbox.objects.get(intento=recepcion.intento)
    if trabajo.publicado_at is not None:
        raise AssertionError("El outbox nació marcado como publicado.")
    resultado_publicacion = publicar_pendientes(limite=1)
    if resultado_publicacion != {"publicados": 1, "errores": 0}:
        raise AssertionError(f"Publicación inesperada: {resultado_publicacion}")

    limite = time.monotonic() + TIEMPO_LIMITE_SEGUNDOS
    while time.monotonic() < limite:
        recepcion.intento.refresh_from_db()
        if recepcion.intento.estado in {"FINALIZADO", "ERROR"}:
            break
        time.sleep(0.2)

    recepcion.captura.refresh_from_db()
    trabajo.refresh_from_db()
    if recepcion.intento.estado != "FINALIZADO":
        raise AssertionError(
            f"El worker no finalizó el intento: {recepcion.intento.estado} "
            f"{recepcion.intento.error_codigo or ''}"
        )
    if recepcion.captura.estado != "COMPLETADA":
        raise AssertionError(f"Captura inesperada: {recepcion.captura.estado}")
    if trabajo.publicado_at is None or trabajo.intentos_publicacion != 1:
        raise AssertionError("El outbox no conserva evidencia de publicación única.")
    if recepcion.intento.resultado_raw.get("schema_version") != "1.0":
        raise AssertionError("El resultado persistido no usa el contrato NLP 1.0.")
    if recepcion.intento.resultado_raw.get("engine", {}).get("mode") != "RULES_ONLY":
        raise AssertionError("El worker no ejecutó RULES_ONLY.")
    if not ItemIA.objects.filter(intento=recepcion.intento).exists():
        raise AssertionError("El worker no persistió la propuesta IA.")

    print(
        "f084-real-ok",
        f"captura={recepcion.captura.id}",
        f"intento={recepcion.intento.id}",
        "postgresql=ok redis=ok worker=ok nlp-wheel=ok",
    )


if __name__ == "__main__":
    ejecutar()
