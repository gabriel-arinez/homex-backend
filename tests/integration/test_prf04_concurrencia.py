from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import close_old_connections
from rest_framework.test import APIClient

from apps.capturas.models import Captura, RevisionAsistida, TrabajoOutbox
from apps.capturas.pipeline import procesar_intento
from apps.proformas.models import DetalleProforma, Proforma
from tests.api.test_ap3_proformas_integrales import payload_integral
from tests.factories import vendedor

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.concurrency]


def test_recepcion_doble_converge_y_captura_se_incorpora_una_vez(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="prf04-concurrencia"))
    entrada = {
        "clave_idempotencia": str(uuid4()),
        "sesion_borrador": str(uuid4()),
        "moneda_codigo": "BOB",
        "texto": "un escritorio con tapa de 25 mm",
    }
    barrera = Barrier(2)

    def recibir(_):
        close_old_connections()
        try:
            api = APIClient()
            api.force_authenticate(actor)
            barrera.wait()
            r = api.post("/api/v1/capturas/asistidas/", entrada, format="json")
            assert r.status_code == 202, r.data
            return r.data
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        respuestas = list(executor.map(recibir, range(2)))
    assert len({r["id"] for r in respuestas}) == 1
    assert {r["reutilizada"] for r in respuestas} == {True, False}
    assert Captura.objects.count() == TrabajoOutbox.objects.count() == 1
    assert procesar_intento(intento_id=respuestas[0]["intento_id"]) == "FINALIZADO"
    barrera = Barrier(2)

    def guardar(_):
        close_old_connections()
        try:
            api = APIClient()
            api.force_authenticate(actor)
            payload = payload_integral(clave=uuid4())
            payload["sesion_borrador"] = entrada["sesion_borrador"]
            payload["detalles"][0]["captura_asistida_id"] = respuestas[0]["id"]
            barrera.wait()
            return api.post("/api/v1/proformas/integral/", payload, format="json").status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        estados = list(executor.map(guardar, range(2)))
    assert sorted(estados) == [201, 409]
    assert (
        Proforma.objects.count()
        == DetalleProforma.objects.count()
        == RevisionAsistida.objects.count()
        == 1
    )
