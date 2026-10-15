"""Regresiones de seguridad e integridad AP4."""
from uuid import uuid4
import pytest
from rest_framework.test import APIClient
from apps.clientes.revision import revision_cliente
from apps.proformas.models import Proforma
from tests.api.test_ap3_proformas_integrales import payload_integral
from tests.factories import cliente_persona, vendedor


@pytest.mark.django_db(transaction=True)
def test_respuesta_opaca_para_referencia_de_cliente(django_user_model):
    propietario = vendedor(django_user_model.objects.create_user(username="ap4-prop"))
    actor = vendedor(django_user_model.objects.create_user(username="ap4-externo"))
    ajeno = cliente_persona(propietario)
    api = APIClient()
    api.force_authenticate(actor)
    for pk in (ajeno.pk, ajeno.pk + 99999):
        body = payload_integral(clave=uuid4())
        body["cliente_nuevo"] = None
        body["cliente"] = pk
        assert api.post("/api/v1/proformas/integral/", body, format="json").status_code == 404
        assert api.post("/api/v1/proformas/", {"cliente": pk, "moneda_codigo": "BOB"}, format="json").status_code == 404
    assert not Proforma.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_cliente_version_obsoleta_no_sobrescribe_edicion(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap4-cas"))
    cliente = cliente_persona(actor)
    api = APIClient()
    api.force_authenticate(actor)
    url = f"/api/v1/clientes/{cliente.pk}/"
    revision = api.get(url).data["revision"]
    nueva = api.patch(url, {"celular": "71234567"}, format="json", HTTP_IF_MATCH=revision)
    assert nueva.status_code == 200, nueva.data
    assert nueva.data["revision"] != revision
    assert api.patch(url, {"direccion": "obsoleta"}, format="json", HTTP_IF_MATCH=revision).status_code == 409
    assert api.delete(url, HTTP_IF_MATCH=revision).status_code == 409
    cliente.refresh_from_db()
    assert cliente.celular == "71234567"
    assert cliente.activo
