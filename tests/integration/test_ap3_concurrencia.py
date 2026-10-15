from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import close_old_connections
from rest_framework.test import APIClient

from apps.proformas.models import Proforma
from tests.factories import cliente_persona, valor, vendedor


@pytest.mark.django_db(transaction=True)
@pytest.mark.concurrency
def test_doble_guardado_integral_concurrente_crea_una_sola_proforma(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap3-concurrente"))
    cliente = cliente_persona(actor, sufijo=" AP3")
    clave = str(uuid4())
    payload = {
        "clave_idempotencia": clave,
        "emitir": False,
        "cliente": cliente.id,
        "titulo": "Guardado concurrente",
        "moneda_codigo": "BOB",
        "detalles": [
            {
                "tipo_item": valor("TIPO_ITEM", "MUEBLE_MEDIDA").id,
                "nombre": "Mesa concurrente",
                "cantidad": "1.0000",
                "unidad": valor("UNIDAD_MEDIDA", "PIEZA").id,
                "modo_calculo": "PRECIO_UNITARIO",
                "precio_unitario": "100.00",
                "importe_negociado": None,
                "descuento": "0.00",
            }
        ],
    }
    barrera = Barrier(2)

    def guardar():
        close_old_connections()
        api = APIClient()
        api.force_authenticate(actor)
        barrera.wait()
        respuesta = api.post("/api/v1/proformas/integral/", payload, format="json")
        close_old_connections()
        return respuesta.status_code, respuesta.data["id"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        resultados = list(executor.map(lambda _: guardar(), range(2)))

    assert {estado for estado, _ in resultados} == {200, 201}
    assert len({proforma_id for _, proforma_id in resultados}) == 1
    assert Proforma.objects.filter(clave_idempotencia=clave).count() == 1
