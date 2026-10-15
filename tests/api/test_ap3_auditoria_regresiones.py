"""Regresiones independientes H01-H05 y H08 tras auditoría AP3."""

from decimal import Decimal
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from apps.clientes.models import Cliente
from apps.proformas.models import DetalleProforma, EspecificacionMueble, Proforma
from apps.proformas.services import agregar_detalle
from tests.api.test_ap3_proformas_integrales import payload_integral
from tests.factories import cliente_persona, valor, vendedor


def api_para(actor):
    api = APIClient()
    api.force_authenticate(actor)
    return api


def datos_actualizacion(proforma, *, clave=None):
    datos = payload_integral(clave=clave or uuid4())
    datos["cliente_nuevo"] = None
    datos["cliente"] = proforma.data["cliente"]
    datos["revision_esperada"] = proforma.data["revision"]
    datos["detalles"][0]["id"] = proforma.data["detalles"][0]["id"]
    return datos


@pytest.mark.django_db(transaction=True)
def test_cliente_ajeno_no_puede_usarse_en_create_integral_o_patch(django_user_model):
    propietario = vendedor(django_user_model.objects.create_user(username="ap3-cliente-dueno"))
    intruso = vendedor(django_user_model.objects.create_user(username="ap3-cliente-intruso"))
    ajeno = cliente_persona(propietario)
    propio = cliente_persona(intruso, sufijo=" autorizado")
    api = api_para(intruso)

    datos = payload_integral(clave=uuid4())
    datos["cliente_nuevo"] = None
    datos["cliente"] = ajeno.id
    assert api.post("/api/v1/proformas/integral/", datos, format="json").status_code == 404
    assert (
        api.post(
            "/api/v1/proformas/",
            {"cliente": ajeno.id, "moneda_codigo": "BOB"},
            format="json",
        ).status_code
        == 404
    )
    assert not Proforma.objects.exists()

    datos["cliente"] = propio.id
    creada = api.post("/api/v1/proformas/integral/", datos, format="json")
    assert creada.status_code == 201
    assert (
        api.patch(
            f"/api/v1/proformas/{creada.data['id']}/",
            {"cliente": ajeno.id},
            format="json",
        ).status_code
        == 404
    )
    assert Proforma.objects.get(pk=creada.data["id"]).cliente_id == propio.id


@pytest.mark.django_db(transaction=True)
def test_revision_emitida_no_puede_quedar_sin_lineas(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap3-integridad"))
    api = api_para(actor)
    creada = api.post(
        "/api/v1/proformas/integral/",
        payload_integral(clave=uuid4(), emitir=True),
        format="json",
    )
    assert creada.status_code == 201
    datos = datos_actualizacion(creada)
    datos["detalles"] = []
    datos["emitir"] = False

    respuesta = api.put(f"/api/v1/proformas/{creada.data['id']}/integral/", datos, format="json")
    assert respuesta.status_code == 409
    assert DetalleProforma.objects.filter(proforma_id=creada.data["id"]).count() == 1

    detalle_id = creada.data["detalles"][0]["id"]
    eliminacion = api.delete(f"/api/v1/proformas-detalle/{detalle_id}/")
    assert eliminacion.status_code == 409
    assert DetalleProforma.objects.filter(pk=detalle_id).exists()


@pytest.mark.django_db(transaction=True)
def test_editor_obsoleto_no_elimina_linea_confirmada_por_hitl(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap3-revision-hitl"))
    api = api_para(actor)
    creada = api.post("/api/v1/proformas/integral/", payload_integral(clave=uuid4()), format="json")
    assert creada.status_code == 201
    datos = datos_actualizacion(creada)

    agregar_detalle(
        proforma_id=creada.data["id"],
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
        nombre="Línea confirmada por HITL",
        cantidad=Decimal("1.0000"),
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("450.00"),
        descuento=Decimal("0.00"),
    )
    respuesta = api.put(f"/api/v1/proformas/{creada.data['id']}/integral/", datos, format="json")
    assert respuesta.status_code == 409
    assert DetalleProforma.objects.filter(proforma_id=creada.data["id"]).count() == 2
    assert DetalleProforma.objects.filter(nombre="Línea confirmada por HITL").exists()


@pytest.mark.django_db(transaction=True)
def test_especificacion_omitida_se_preserva_y_null_expresa_eliminacion(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap3-spec-omision"))
    api = api_para(actor)
    creada = api.post("/api/v1/proformas/integral/", payload_integral(clave=uuid4()), format="json")
    assert creada.status_code == 201
    datos = datos_actualizacion(creada)
    datos["detalles"][0].pop("especificacion")
    respuesta = api.put(f"/api/v1/proformas/{creada.data['id']}/integral/", datos, format="json")
    assert respuesta.status_code == 200
    ficha = EspecificacionMueble.objects.get(proforma_detalle_id=creada.data["detalles"][0]["id"])
    assert ficha.datos_tecnicos["componentes"][0]["atributo_abierto"] == {"canto": "2 mm"}


@pytest.mark.django_db(transaction=True)
def test_linea_historica_negociada_no_se_convierte_en_integral(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap3-legacy-negociado"))
    api = api_para(actor)
    creada = api.post("/api/v1/proformas/integral/", payload_integral(clave=uuid4()), format="json")
    assert creada.status_code == 201
    detalle_id = creada.data["detalles"][0]["id"]
    DetalleProforma.objects.filter(pk=detalle_id).update(
        modo_calculo="TOTAL_NEGOCIADO",
        importe_negociado=Decimal("2500.00"),
        precio_unitario=Decimal("0.00"),
    )
    vigente = api.get(f"/api/v1/proformas/{creada.data['id']}/")
    datos = datos_actualizacion(vigente)
    datos["detalles"][0].update(
        modo_calculo="TOTAL_NEGOCIADO",
        precio_unitario="0.00",
        importe_negociado="2500.00",
    )
    respuesta = api.put(f"/api/v1/proformas/{creada.data['id']}/integral/", datos, format="json")
    assert respuesta.status_code == 200
    detalle = DetalleProforma.objects.get(pk=detalle_id)
    assert detalle.modo_calculo == "TOTAL_NEGOCIADO"
    assert detalle.importe_negociado == Decimal("2500.00")
    assert detalle.total == Decimal("2500.00")


@pytest.mark.django_db(transaction=True)
def test_cliente_empresa_puede_emitir_por_razon_social(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap3-empresa"))
    api = api_para(actor)
    datos = payload_integral(clave=uuid4(), emitir=True)
    datos["cliente_nuevo"] = {
        "tipo_cliente": valor("TIPO_CLIENTE", "EMPRESA").id,
        "empresa": "Muebles Andinos SRL",
        "nombres": "Elena",
        "apellidos": "Quispe",
    }
    respuesta = api.post("/api/v1/proformas/integral/", datos, format="json")
    assert respuesta.status_code == 201, respuesta.data
    assert respuesta.data["estado_info"]["codigo"] == "EN_REVISION"
    assert Cliente.objects.get(pk=respuesta.data["cliente"]).empresa == "Muebles Andinos SRL"
