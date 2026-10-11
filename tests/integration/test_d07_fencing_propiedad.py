from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Event
from uuid import uuid4

import pytest
from django.db import close_old_connections, connection
from django.test import override_settings
from django.utils import timezone

from apps.capturas.models import IntentoCaptura, ItemIA, TrabajoOutbox
from apps.capturas.nlp.adapter import AdaptadorNLP
from apps.capturas.outbox import reconciliar_publicados
from apps.capturas.pipeline import procesar_intento
from apps.capturas.services import recibir_captura_texto
from apps.proformas.services import crear_proforma
from tests.factories import cliente_persona, vendedor


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("worker_obsoleto_falla", [False, True])
def test_worker_obsoleto_no_puede_cerrar_intento_vigente(django_user_model, worker_obsoleto_falla):
    actor = vendedor(
        django_user_model.objects.create_user(username=f"d07-fencing-{worker_obsoleto_falla}")
    )
    proforma = crear_proforma(
        actor=actor,
        cliente=cliente_persona(actor, sufijo=f"d07-fencing-{worker_obsoleto_falla}"),
    )
    recepcion = recibir_captura_texto(
        actor=actor,
        clave_idempotencia=uuid4(),
        proforma_id=proforma.id,
        texto="Tres escritorios, total cien bolivianos",
    )

    intento_id = recepcion.intento.pk
    trabajo = TrabajoOutbox.objects.get(intento_id=intento_id)

    inicio_a = Event()
    liberar_a = Event()
    inicio_b = Event()
    liberar_b = Event()

    class NLPControlado:
        def __init__(self, etiqueta):
            self.etiqueta = etiqueta

        def extraer(self, **kwargs):
            if self.etiqueta == "A":
                # Pierde la sesión que mantenía el advisory lock.
                connection.close()
                inicio_a.set()
                if not liberar_a.wait(timeout=15):
                    raise AssertionError("Timeout worker A")

                if worker_obsoleto_falla:
                    raise RuntimeError("fallo NLP del worker obsoleto")

            if self.etiqueta == "B":
                inicio_b.set()
                if not liberar_b.wait(timeout=15):
                    raise AssertionError("Timeout worker B")

            resultado = AdaptadorNLP().extraer(**kwargs)
            assert resultado.propuesta is not None

            propuesta = replace(
                resultado.propuesta,
                nombre=f"RESULTADO_WORKER_{self.etiqueta}",
            )

            return replace(resultado, propuesta=propuesta)

    def ejecutar(etiqueta):
        close_old_connections()
        try:
            return procesar_intento(
                intento_id=intento_id,
                adaptador_nlp=NLPControlado(etiqueta),
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futuro_a = executor.submit(ejecutar, "A")

        try:
            assert inicio_a.wait(timeout=10)

            intento = IntentoCaptura.objects.get(pk=intento_id)
            assert intento.estado == "PROCESANDO"
            token_a = intento.ejecucion_token
            assert token_a is not None

            TrabajoOutbox.objects.filter(pk=trabajo.pk).update(
                publicado_at=timezone.now() - timedelta(hours=2)
            )

            with override_settings(HOMEX_OUTBOX_RECONCILE_SECONDS=3600):
                assert reconciliar_publicados() == 1

            intento.refresh_from_db()
            assert intento.estado == "PENDIENTE"
            assert intento.ejecucion_token is None

            futuro_b = executor.submit(ejecutar, "B")
            assert inicio_b.wait(timeout=10)

            intento.refresh_from_db()
            token_b = intento.ejecucion_token

            assert intento.estado == "PROCESANDO"
            assert token_b is not None
            assert token_b != token_a

            # A termina (o falla) antes de que B termine.
            liberar_a.set()
            resultado_a = futuro_a.result(timeout=12)

            intento.refresh_from_db()
            assert intento.estado == "PROCESANDO"
            assert intento.ejecucion_token == token_b
            assert intento.error_codigo is None
            assert not ItemIA.objects.filter(intento_id=intento_id).exists()

            print(
                "PASS: worker A obsoleto no alteró estado ni resultado",
                "fallo_nlp=",
                worker_obsoleto_falla,
                "retorno=",
                resultado_a,
                flush=True,
            )

        finally:
            liberar_a.set()
            liberar_b.set()

        resultado_b = futuro_b.result(timeout=12)

    intento.refresh_from_db()
    item = ItemIA.objects.get(intento_id=intento_id)

    assert resultado_b == "FINALIZADO"
    assert intento.estado == "FINALIZADO"
    assert intento.error_codigo is None
    assert intento.ejecucion_token == token_b
    assert item.nombre == "RESULTADO_WORKER_B"

    print(
        "PASS: resultado persistido pertenece exclusivamente a B",
        flush=True,
    )
