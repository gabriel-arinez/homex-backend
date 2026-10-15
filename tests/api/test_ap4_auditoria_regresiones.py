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
        assert (
            api.post(
                "/api/v1/proformas/",
                {"cliente": pk, "moneda_codigo": "BOB"},
                format="json",
            ).status_code
            == 404
        )
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
    assert (
        api.patch(url, {"direccion": "obsoleta"}, format="json", HTTP_IF_MATCH=revision).status_code
        == 409
    )
    assert api.delete(url, HTTP_IF_MATCH=revision).status_code == 409
    cliente.refresh_from_db()
    assert cliente.celular == "71234567"
    assert cliente.activo


@pytest.mark.django_db(transaction=True)
def test_cliente_inactivo_se_conserva_en_proforma_preexistente(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap4-inactivo"))
    cliente = cliente_persona(actor)
    api = APIClient()
    api.force_authenticate(actor)
    cuerpo = payload_integral(clave=uuid4(), emitir=True)
    cuerpo["cliente_nuevo"] = None
    cuerpo["cliente"] = cliente.pk
    creada = api.post("/api/v1/proformas/integral/", cuerpo, format="json")
    assert creada.status_code == 201, creada.data
    assert (
        api.delete(
            f"/api/v1/clientes/{cliente.pk}/", HTTP_IF_MATCH=revision_cliente(cliente)
        ).status_code
        == 204
    )

    cuerpo["detalles"][0]["id"] = creada.data["detalles"][0]["id"]
    cuerpo["revision_esperada"] = creada.data["revision"]
    cuerpo["emitir"] = False
    cuerpo["observaciones"] = "Corregir observación sin cambiar cliente"
    actualizada = api.put(f"/api/v1/proformas/{creada.data['id']}/integral/", cuerpo, format="json")
    assert actualizada.status_code == 200, actualizada.data
    assert actualizada.data["cliente"] == cliente.pk

    nuevo = payload_integral(clave=uuid4())
    nuevo["cliente_nuevo"] = None
    nuevo["cliente"] = cliente.pk
    assert api.post("/api/v1/proformas/integral/", nuevo, format="json").status_code == 404


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("tipo_empresa", [False, True])
def test_emision_real_preserva_snapshots_tras_actualizar_y_desactivar(
    django_user_model, tipo_empresa
):
    from apps.clientes.models import Cliente
    from tests.factories import valor

    actor = vendedor(django_user_model.objects.create_user(username=f"ap4-snapshot-{tipo_empresa}"))
    api = APIClient()
    api.force_authenticate(actor)
    if tipo_empresa:
        resultado = api.post(
            "/api/v1/clientes/",
            {
                "tipo_cliente": valor("TIPO_CLIENTE", "EMPRESA").pk,
                "empresa": "HOMEX Clientes SRL",
                "nombres": "Elena",
                "apellidos": "Mendoza",
                "celular": "75555555",
                "direccion": "Calle Sucre",
            },
            format="json",
        )
        assert resultado.status_code == 201, resultado.data
        cliente = Cliente.objects.get(pk=resultado.data["id"])
    else:
        cliente = cliente_persona(actor)
        cliente.celular = "75555555"
        cliente.direccion = "Calle Sucre"
        cliente.save(update_fields=["celular", "direccion"])

    datos = payload_integral(clave=uuid4(), emitir=True)
    datos["cliente_nuevo"] = None
    datos["cliente"] = cliente.pk
    creada = api.post("/api/v1/proformas/integral/", datos, format="json")
    assert creada.status_code == 201, creada.data
    proforma = Proforma.objects.get(pk=creada.data["id"])
    campos = (
        "cliente_nombre_snapshot",
        "cliente_empresa_snapshot",
        "cliente_celular_snapshot",
        "cliente_direccion_snapshot",
    )
    previos = {campo: getattr(proforma, campo) for campo in campos}
    assert previos["cliente_nombre_snapshot"]
    assert previos["cliente_celular_snapshot"] == "75555555"
    assert previos["cliente_direccion_snapshot"] == "Calle Sucre"
    if tipo_empresa:
        assert previos["cliente_empresa_snapshot"] == "HOMEX Clientes SRL"

    editada = api.patch(
        f"/api/v1/clientes/{cliente.pk}/",
        {
            "nombres": "Nueva",
            "apellidos": "Identidad",
            "empresa": "Otra empresa" if tipo_empresa else None,
            "celular": "72222222",
            "direccion": "Otra calle",
        },
        format="json",
        HTTP_IF_MATCH=revision_cliente(cliente),
    )
    assert editada.status_code == 200, editada.data
    assert (
        api.delete(
            f"/api/v1/clientes/{cliente.pk}/", HTTP_IF_MATCH=editada.data["revision"]
        ).status_code
        == 204
    )
    proforma.refresh_from_db()
    assert {campo: getattr(proforma, campo) for campo in campos} == previos
