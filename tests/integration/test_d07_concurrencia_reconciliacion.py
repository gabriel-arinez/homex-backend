from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event, Lock

import pytest
from django.db import close_old_connections
from django.utils import timezone

from apps.capturas.models import IntentoCaptura, ItemIA, TrabajoOutbox
from apps.capturas.nlp.adapter import AdaptadorNLP
from apps.capturas.outbox import reconciliar_publicados
from apps.capturas.pipeline import procesar_intento
from apps.capturas.services import recibir_captura_texto
from apps.proformas.services import crear_proforma
from tests.factories import cliente_persona, vendedor


@pytest.mark.django_db(transaction=True)
def test_reconciliacion_con_worker_original_activo(django_user_model):
    actor = vendedor(
        django_user_model.objects.create_user(username="d07-reconciliacion-concurrente")
    )

    proforma = crear_proforma(
        actor=actor,
        cliente=cliente_persona(
            actor,
            sufijo="d07-reconciliacion-concurrente",
        ),
    )

    from uuid import uuid4

    recepcion = recibir_captura_texto(
        actor=actor,
        clave_idempotencia=uuid4(),
        proforma_id=proforma.id,
        texto="Tres escritorios, total cien bolivianos",
    )

    intento_id = recepcion.intento.id
    trabajo = TrabajoOutbox.objects.get(intento_id=intento_id)

    inicio_nlp_original = Event()
    liberar_nlp_original = Event()
    candado = Lock()
    ejecuciones_nlp = []

    class AdaptadorControlado:
        def __init__(self, etiqueta, bloquear=False):
            self.etiqueta = etiqueta
            self.bloquear = bloquear

        def extraer(self, **kwargs):
            with candado:
                ejecuciones_nlp.append(self.etiqueta)

            if self.bloquear:
                inicio_nlp_original.set()
                if not liberar_nlp_original.wait(timeout=15):
                    raise RuntimeError("Timeout esperando liberación del NLP original")

            return AdaptadorNLP().extraer(**kwargs)

    def ejecutar(adaptador):
        close_old_connections()
        try:
            return procesar_intento(
                intento_id=intento_id,
                adaptador_nlp=adaptador,
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        original = executor.submit(
            ejecutar,
            AdaptadorControlado("worker_original", bloquear=True),
        )

        try:
            assert inicio_nlp_original.wait(timeout=10), "El procesamiento original no alcanzó NLP"

            intento = IntentoCaptura.objects.get(pk=intento_id)
            assert intento.estado == "PROCESANDO"

            print(
                "PASS: worker original activo en NLP",
                flush=True,
            )

            TrabajoOutbox.objects.filter(pk=trabajo.pk).update(
                publicado_at=timezone.now() - timedelta(hours=2)
            )

            from django.test import override_settings

            with override_settings(HOMEX_OUTBOX_RECONCILE_SECONDS=3600):
                reconciliados = reconciliar_publicados()

            assert reconciliados == 0

            intento.refresh_from_db()
            assert intento.estado == "PROCESANDO"

            print(
                "PASS: reconciliador no reinicia NLP activo",
                flush=True,
            )

            segundo = executor.submit(
                ejecutar,
                AdaptadorControlado("worker_republicado"),
            )

            resultado_segundo = segundo.result(timeout=12)

        finally:
            liberar_nlp_original.set()

        resultado_original = original.result(timeout=12)

    intento.refresh_from_db()

    cantidad_items = ItemIA.objects.filter(intento_id=intento_id).count()

    print("Resultado worker original:", resultado_original)
    print("Resultado worker republicado:", resultado_segundo)
    print("Estado final:", intento.estado)
    print("Número de ejecuciones NLP:", len(ejecuciones_nlp))
    print("Ejecuciones:", ejecuciones_nlp)
    print("Resultados ItemIA:", cantidad_items)

    assert intento.estado == "FINALIZADO"
    assert resultado_segundo == "PROCESANDO"
    assert resultado_original == "FINALIZADO"
    assert cantidad_items <= 1

    if len(ejecuciones_nlp) > 1:
        print(
            "RIESGO REPRODUCIDO: dos workers ejecutaron NLP "
            "para el mismo intento durante la reconciliación",
            flush=True,
        )
    else:
        print(
            "PASS: no se observó ejecución NLP duplicada",
            flush=True,
        )

    assert len(ejecuciones_nlp) == 1, (
        "REGRESION: la reconciliación permitió dos ejecuciones NLP para el mismo intento"
    )

    print("homex-d07-concurrencia-escenario-completado")
