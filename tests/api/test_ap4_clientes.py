import pytest
from rest_framework.test import APIClient

from apps.clientes.models import Cliente
from apps.clientes.revision import revision_cliente
from apps.proformas.models import Proforma
from apps.proformas.services import crear_proforma
from tests.factories import cliente_persona, valor, vendedor


@pytest.mark.django_db
def test_ap4_crea_persona_y_empresa_con_tipo_legible(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap4-create"))
    api = APIClient()
    api.force_authenticate(actor)

    persona = api.post(
        "/api/v1/clientes/",
        {
            "tipo_cliente": valor("TIPO_CLIENTE", "PERSONA").id,
            "nombres": "Ana",
            "apellidos": "López",
            "celular": "70000000",
        },
        format="json",
    )
    assert persona.status_code == 201
    assert persona.data["tipo_cliente_info"]["codigo"] == "PERSONA"

    empresa = api.post(
        "/api/v1/clientes/",
        {
            "tipo_cliente": valor("TIPO_CLIENTE", "EMPRESA").id,
            "empresa": "Muebles Sur",
            "nombres": "María",
            "apellidos": "Quispe",
        },
        format="json",
    )
    assert empresa.status_code == 201
    assert empresa.data["tipo_cliente_info"]["nombre"] == "Empresa"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("codigo", "payload", "campo"),
    [
        ("PERSONA", {"nombres": "", "apellidos": "López"}, "nombres"),
        ("PERSONA", {"nombres": "Ana", "apellidos": ""}, "apellidos"),
        ("PERSONA", {"nombres": "Ana", "apellidos": "López", "empresa": "No aplica"}, "empresa"),
        ("EMPRESA", {"nombres": "Ana", "apellidos": "López", "empresa": ""}, "empresa"),
    ],
)
def test_ap4_rechaza_identidad_incompleta(django_user_model, codigo, payload, campo):
    actor = vendedor(
        django_user_model.objects.create_user(username=f"ap4-invalid-{codigo}-{campo}")
    )
    api = APIClient()
    api.force_authenticate(actor)
    respuesta = api.post(
        "/api/v1/clientes/",
        {"tipo_cliente": valor("TIPO_CLIENTE", codigo).id, **payload},
        format="json",
    )
    assert respuesta.status_code == 400
    assert campo in respuesta.data


@pytest.mark.django_db
def test_ap4_tipo_es_inmutable_y_delete_desactiva_sin_borrar(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap4-state"))
    registro = cliente_persona(actor)
    api = APIClient()
    api.force_authenticate(actor)

    cambio = api.patch(
        f"/api/v1/clientes/{registro.id}/",
        {"tipo_cliente": valor("TIPO_CLIENTE", "EMPRESA").id, "empresa": "Empresa"},
        format="json",
    )
    assert cambio.status_code == 400
    assert "tipo_cliente" in cambio.data

    assert api.delete(
        f"/api/v1/clientes/{registro.id}/", HTTP_IF_MATCH=revision_cliente(registro)
    ).status_code == 204
    registro.refresh_from_db()
    assert registro.activo is False
    assert Cliente.objects.filter(pk=registro.id).exists()


@pytest.mark.django_db
def test_ap4_actualizar_cliente_no_reescribe_snapshot(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap4-snapshot"))
    registro = cliente_persona(actor)
    proforma = crear_proforma(actor=actor, cliente=registro)
    proforma.cliente_nombre_snapshot = "Ana López"
    proforma.cliente_empresa_snapshot = None
    proforma.save(update_fields=["cliente_nombre_snapshot", "cliente_empresa_snapshot"])
    api = APIClient()
    api.force_authenticate(actor)
    respuesta = api.patch(
        f"/api/v1/clientes/{registro.id}/",
        {"nombres": "Ana María"},
        format="json",
        HTTP_IF_MATCH=revision_cliente(registro),
    )
    assert respuesta.status_code == 200
    proforma.refresh_from_db()
    assert proforma.cliente_nombre_snapshot == "Ana López"


@pytest.mark.django_db
def test_ap4_proforma_integral_rechaza_cliente_ajeno(django_user_model):
    propietario = vendedor(django_user_model.objects.create_user(username="ap4-owner"))
    actor = vendedor(django_user_model.objects.create_user(username="ap4-other"))
    ajeno = cliente_persona(propietario)
    api = APIClient()
    api.force_authenticate(actor)
    respuesta = api.post(
        "/api/v1/proformas/integral/",
        {
            "clave_idempotencia": "9da45af7-92f2-4e7b-89a8-b68dd47af0b4",
            "emitir": False,
            "cliente": ajeno.id,
            "cliente_nuevo": None,
            "moneda_codigo": "BOB",
            "detalles": [],
        },
        format="json",
    )
    assert respuesta.status_code == 404
    assert Proforma.objects.count() == 0
