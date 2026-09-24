from threading import Barrier, Lock, Thread
from uuid import uuid4

import pytest
from django.db import close_old_connections
from django.utils import timezone

from apps.capturas.models import Captura, IntentoCaptura, TrabajoOutbox
from apps.capturas.services import crear_intento, recibir_captura_texto
from apps.proformas.services import crear_proforma
from tests.factories import cliente_persona


@pytest.mark.concurrency
@pytest.mark.django_db(transaction=True)
def test_dos_post_con_misma_clave_convergen_en_una_captura(django_user_model):
    actor = django_user_model.objects.create_user(username="f081-concurrente")
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    clave = uuid4()
    barrera = Barrier(3)
    candado = Lock()
    resultados = []
    errores = []

    def ejecutar():
        close_old_connections()
        try:
            usuario = django_user_model.objects.get(pk=actor.pk)
            barrera.wait(timeout=5)
            recepcion = recibir_captura_texto(
                actor=usuario,
                clave_idempotencia=clave,
                proforma_id=proforma.id,
                texto="Dos sillas negras",
            )
            with candado:
                resultados.append((recepcion.captura.id, recepcion.reutilizada))
        except Exception as exc:
            with candado:
                errores.append(exc)
        finally:
            close_old_connections()

    hilos = [Thread(target=ejecutar, daemon=True) for _ in range(2)]
    for hilo in hilos:
        hilo.start()
    barrera.wait(timeout=5)
    for hilo in hilos:
        hilo.join(timeout=10)

    assert not any(hilo.is_alive() for hilo in hilos)
    assert errores == []
    assert len(resultados) == 2
    assert len({resultado[0] for resultado in resultados}) == 1
    assert sorted(resultado[1] for resultado in resultados) == [False, True]
    assert Captura.objects.count() == 1
    assert IntentoCaptura.objects.count() == 1
    assert TrabajoOutbox.objects.count() == 1


@pytest.mark.concurrency
@pytest.mark.django_db(transaction=True)
def test_dos_intentos_concurrentes_reciben_numeros_distintos(django_user_model):
    actor = django_user_model.objects.create_user(username="f081-intentos-concurrentes")
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    captura = Captura.objects.create(
        proforma=proforma,
        vendedor=actor,
        clave_idempotencia=uuid4(),
        estado="PENDIENTE",
        capturado_at=timezone.now(),
        texto_transcrito="Captura con reintentos concurrentes",
        created_by=actor,
        updated_by=actor,
    )
    barrera = Barrier(3)
    candado = Lock()
    numeros = []
    errores = []

    def ejecutar(input_hash):
        close_old_connections()
        try:
            barrera.wait(timeout=5)
            intento = crear_intento(captura_id=captura.id, input_hash=input_hash)
            with candado:
                numeros.append(intento.numero_intento)
        except Exception as exc:
            with candado:
                errores.append(exc)
        finally:
            close_old_connections()

    hilos = [
        Thread(target=ejecutar, args=("a" * 64,), daemon=True),
        Thread(target=ejecutar, args=("b" * 64,), daemon=True),
    ]
    for hilo in hilos:
        hilo.start()
    barrera.wait(timeout=5)
    for hilo in hilos:
        hilo.join(timeout=10)

    assert not any(hilo.is_alive() for hilo in hilos)
    assert errores == []
    assert sorted(numeros) == [1, 2]
    assert IntentoCaptura.objects.filter(captura=captura).count() == 2
    assert TrabajoOutbox.objects.filter(intento__captura=captura).count() == 2
    assert list(
        TrabajoOutbox.objects.filter(intento__captura=captura)
        .order_by("intento__numero_intento")
        .values_list("clave_unica", flat=True)
    ) == [
        f"captura:{captura.id}:intento:1",
        f"captura:{captura.id}:intento:2",
    ]
