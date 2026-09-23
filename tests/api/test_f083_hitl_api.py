import pytest
from rest_framework.test import APIClient

from apps.capturas.models import EvaluacionNLP, ItemHumano
from tests.integration.test_f083_hitl import escenario_hitl, payload_confirmacion


@pytest.mark.django_db(transaction=True)
def test_get_captura_entrega_original_persistido_del_servidor(django_user_model):
    actor, _, captura, intento, item_ia = escenario_hitl(django_user_model, "f083-api-get")
    cliente = APIClient()
    cliente.force_authenticate(actor)
    respuesta = cliente.get(f"/api/v1/capturas/{captura.id}/")
    assert respuesta.status_code == 200
    assert respuesta.data["intento_id"] == intento.id
    assert respuesta.data["item_ia"]["id"] == item_ia.id
    assert respuesta.data["item_ia"]["nombre"] == "Mesa a medida"
    assert respuesta.data["incorporada"] is False


@pytest.mark.django_db(transaction=True)
def test_api_rechaza_original_ia_enviado_por_navegador(django_user_model):
    actor, _, captura, intento, item_ia = escenario_hitl(django_user_model, "f083-api-manipulado")
    cliente = APIClient()
    cliente.force_authenticate(actor)
    payload = payload_confirmacion(intento, item_ia)
    payload["original_ia"] = {"nombre": "Original manipulado"}
    respuesta = cliente.post(f"/api/v1/capturas/{captura.id}/confirmar/", payload, format="json")
    assert respuesta.status_code == 400
    assert not ItemHumano.objects.exists()
    assert not EvaluacionNLP.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_api_confirma_y_segundo_post_devuelve_409(django_user_model):
    actor, proforma, captura, intento, item_ia = escenario_hitl(
        django_user_model, "f083-api-confirmar"
    )
    cliente = APIClient()
    cliente.force_authenticate(actor)
    payload = payload_confirmacion(intento, item_ia)
    url = f"/api/v1/capturas/{captura.id}/confirmar/"
    primera = cliente.post(url, payload, format="json")
    segunda = cliente.post(url, payload, format="json")
    assert primera.status_code == 201
    assert segunda.status_code == 409
    proforma.refresh_from_db()
    assert primera.data["proforma_estado"] == proforma.estado.codigo == "BORRADOR"


@pytest.mark.django_db(transaction=True)
def test_vendedor_no_consulta_ni_confirma_captura_ajena(django_user_model):
    propietario, _, captura, intento, item_ia = escenario_hitl(
        django_user_model, "f083-api-propietario"
    )
    ajeno, _, _, _, _ = escenario_hitl(django_user_model, "f083-api-ajeno")
    cliente = APIClient()
    cliente.force_authenticate(ajeno)
    assert cliente.get(f"/api/v1/capturas/{captura.id}/").status_code == 404
    assert (
        cliente.post(
            f"/api/v1/capturas/{captura.id}/confirmar/",
            payload_confirmacion(intento, item_ia),
            format="json",
        ).status_code
        == 404
    )
