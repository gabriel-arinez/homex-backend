from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from apps.capturas.models import Captura, IntentoCaptura, TrabajoOutbox
from apps.proformas.services import crear_proforma
from tests.factories import cliente_persona, vendedor


@pytest.mark.django_db(transaction=True)
def test_post_captura_es_idempotente_y_crea_un_solo_trabajo(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="captura-api"))
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    clave = str(uuid4())
    payload = {
        "clave_idempotencia": clave,
        "proforma": proforma.id,
        "texto": "Tres muebles por cien bolivianos",
    }
    cliente = APIClient()
    cliente.force_authenticate(actor)

    primera = cliente.post("/api/v1/capturas/", payload, format="json")
    segunda = cliente.post("/api/v1/capturas/", payload, format="json")

    assert primera.status_code == segunda.status_code == 202
    assert primera.data["id"] == segunda.data["id"]
    assert primera.data["intento_id"] == segunda.data["intento_id"]
    assert primera.data["reutilizada"] is False
    assert segunda.data["reutilizada"] is True
    assert Captura.objects.count() == 1
    assert IntentoCaptura.objects.count() == 1
    assert TrabajoOutbox.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_clave_reutilizada_con_contenido_incompatible_devuelve_409(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="captura-conflicto"))
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    clave = str(uuid4())
    cliente = APIClient()
    cliente.force_authenticate(actor)

    original = cliente.post(
        "/api/v1/capturas/",
        {"clave_idempotencia": clave, "proforma": proforma.id, "texto": "Una silla"},
        format="json",
    )
    conflicto = cliente.post(
        "/api/v1/capturas/",
        {"clave_idempotencia": clave, "proforma": proforma.id, "texto": "Dos sillas"},
        format="json",
    )

    assert original.status_code == 202
    assert conflicto.status_code == 409
    assert conflicto.data["detail"].code == "conflicto_idempotencia"


@pytest.mark.django_db(transaction=True)
def test_clave_no_puede_reutilizarse_por_otro_actor(django_user_model):
    propietario = vendedor(django_user_model.objects.create_user(username="captura-propietario"))
    ajeno = vendedor(django_user_model.objects.create_user(username="captura-ajeno"))
    proforma = crear_proforma(actor=propietario, cliente=cliente_persona(propietario))
    clave = str(uuid4())
    payload = {"clave_idempotencia": clave, "proforma": proforma.id, "texto": "Una silla"}
    cliente = APIClient()
    cliente.force_authenticate(propietario)
    assert cliente.post("/api/v1/capturas/", payload, format="json").status_code == 202

    cliente.force_authenticate(ajeno)
    respuesta = cliente.post("/api/v1/capturas/", payload, format="json")
    assert respuesta.status_code == 409
