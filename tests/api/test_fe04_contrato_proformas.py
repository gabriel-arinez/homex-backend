from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from apps.pedidos.models import Pedido
from apps.proformas.services import (
    agregar_detalle,
    crear_proforma,
    enviar_proforma,
)
from tests.factories import cargar_stock, cliente_persona, silla, valor, vendedor


def _detalle_basico(*, proforma, actor, nombre="Elemento"):
    producto = silla(
        actor,
        sku=f"FE04-{proforma.id}",
        precio="100.00",
    )
    cargar_stock(producto, actor, 5)
    return agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "SILLA"),
        producto_id=producto.id,
        nombre=nombre,
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("100.00"),
    )


def _imagen():
    salida = BytesIO()
    Image.new("RGB", (320, 240), "red").save(salida, format="JPEG")
    return SimpleUploadedFile(
        "referencia.jpg",
        salida.getvalue(),
        content_type="image/jpeg",
    )


@pytest.mark.django_db(transaction=True)
def test_proformas_listado_paginado_busca_filtra_y_expone_semantica(django_user_model):
    propietario = vendedor(django_user_model.objects.create_user(username="fe04-list-owner"))
    ajeno = vendedor(django_user_model.objects.create_user(username="fe04-list-other"))

    cliente = cliente_persona(propietario, sufijo=" FE04")
    propia = crear_proforma(
        actor=propietario,
        cliente=cliente,
        titulo="Proyecto Directorio",
        moneda_codigo="USD",
    )
    crear_proforma(
        actor=propietario,
        cliente=cliente,
        titulo="Proyecto auxiliar",
        moneda_codigo="BOB",
    )
    crear_proforma(
        actor=ajeno,
        cliente=cliente_persona(ajeno, sufijo=" Ajeno"),
        titulo="Proyecto Directorio Ajeno",
        moneda_codigo="USD",
    )

    api = APIClient()
    api.force_authenticate(propietario)
    respuesta = api.get(
        "/api/v1/proformas/",
        {
            "search": "Directorio",
            "estado": "BORRADOR",
            "moneda": "USD",
            "cliente": cliente.id,
            "page": 1,
            "page_size": 1,
        },
    )

    assert respuesta.status_code == 200
    assert respuesta.data["count"] == 1
    assert respuesta.data["next"] is None
    assert respuesta.data["previous"] is None
    assert len(respuesta.data["results"]) == 1

    item = respuesta.data["results"][0]
    assert item["id"] == propia.id
    assert item["estado_info"] == {
        "id": valor("ESTADO_PROFORMA", "BORRADOR").id,
        "codigo": "BORRADOR",
        "nombre": "Borrador",
    }
    assert item["moneda_info"]["codigo"] == "USD"
    assert item["cliente_resumen"]["id"] == cliente.id
    assert "Ana" in item["cliente_resumen"]["nombre"]
    assert "detalles" not in item

    por_numero = api.get(
        "/api/v1/proformas/",
        {
            "search": str(propia.numero),
            "page_size": 20,
        },
    )
    assert por_numero.status_code == 200
    assert por_numero.data["count"] == 1
    assert por_numero.data["results"][0]["id"] == propia.id


@pytest.mark.django_db
def test_catalogo_opciones_publica_codigos_y_etiquetas_para_fe04(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="fe04-catalogos"))
    valor("TIPO_ITEM", "MUEBLE_MEDIDA")
    valor("TIPO_ITEM", "SILLA")
    valor("UNIDAD_MEDIDA", "PIEZA")
    valor("TIPO_MUEBLE", "MESA_REUNION")
    valor("MONEDA", "BOB")
    valor("ESTADO_PROFORMA", "BORRADOR")

    api = APIClient()
    api.force_authenticate(actor)

    respuesta = api.get("/api/v1/catalogo/opciones/", {"concepto": "TIPO_ITEM"})
    assert respuesta.status_code == 200
    assert {item["codigo"] for item in respuesta.data} >= {"MUEBLE_MEDIDA", "SILLA"}
    assert all(item["concepto_codigo"] == "TIPO_ITEM" for item in respuesta.data)
    assert all(
        {"id", "concepto_codigo", "codigo", "nombre"} <= set(item) for item in respuesta.data
    )

    assert api.get("/api/v1/catalogo/opciones/").status_code == 400
    assert (
        api.get("/api/v1/catalogo/opciones/", {"concepto": "CATALOGO_PRIVADO"}).status_code == 400
    )


@pytest.mark.django_db(transaction=True)
def test_enviada_congela_proforma_detalles_especificacion_y_adjuntos(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="fe04-freeze"))
    proforma = crear_proforma(
        actor=actor,
        cliente=cliente_persona(actor),
    )
    detalle = _detalle_basico(proforma=proforma, actor=actor)

    api = APIClient()
    api.force_authenticate(actor)

    adjunto_creado = api.post(
        f"/api/v1/proformas/{proforma.id}/detalles/{detalle.id}/archivos/",
        {"archivo": _imagen()},
        format="multipart",
    )
    assert adjunto_creado.status_code == 201
    archivo_id = adjunto_creado.data["id"]

    enviar_proforma(proforma_id=proforma.id, actor=actor)

    assert (
        api.patch(
            f"/api/v1/proformas/{proforma.id}/",
            {"titulo": "No debe cambiar"},
            format="json",
        ).status_code
        == 409
    )
    assert (
        api.post(
            f"/api/v1/proformas/{proforma.id}/detalles/",
            {
                "tipo_item": valor("TIPO_ITEM", "OTRO").id,
                "nombre": "Nuevo",
                "cantidad": 1,
                "unidad": valor("UNIDAD_MEDIDA", "PIEZA").id,
                "modo_calculo": "PRECIO_UNITARIO",
                "precio_unitario": "10.00",
                "descuento": "0.00",
            },
            format="json",
        ).status_code
        == 409
    )
    assert (
        api.patch(
            f"/api/v1/proformas-detalle/{detalle.id}/",
            {"cantidad": 2},
            format="json",
        ).status_code
        == 409
    )
    assert (
        api.post(
            f"/api/v1/proformas-detalle/{detalle.id}/especificacion/",
            {"schema_version": 1},
            format="json",
        ).status_code
        == 409
    )
    assert (
        api.post(
            f"/api/v1/proformas/{proforma.id}/detalles/{detalle.id}/archivos/",
            {"archivo": _imagen()},
            format="multipart",
        ).status_code
        == 409
    )
    assert (
        api.delete(
            f"/api/v1/proformas/{proforma.id}/detalles/{detalle.id}/archivos/{archivo_id}/"
        ).status_code
        == 409
    )
    assert api.post(f"/api/v1/proformas/{proforma.id}/enviar/").status_code == 409


@pytest.mark.django_db(transaction=True)
def test_mismo_vendedor_puede_aprobar_propia_y_doble_aprobacion_es_409(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="fe04-aprobar"))
    proforma = crear_proforma(
        actor=actor,
        cliente=cliente_persona(actor),
    )
    _detalle_basico(proforma=proforma, actor=actor)

    api = APIClient()
    api.force_authenticate(actor)

    assert api.post(f"/api/v1/proformas/{proforma.id}/enviar/").status_code == 200

    respuesta = api.post(f"/api/v1/proformas/{proforma.id}/aprobar/")
    assert respuesta.status_code == 200
    assert respuesta.data["estado"] == "CONFIRMADO"
    assert Pedido.objects.filter(
        id=respuesta.data["pedido_id"],
        proforma=proforma,
    ).exists()

    repetida = api.post(f"/api/v1/proformas/{proforma.id}/aprobar/")
    assert repetida.status_code == 409
    assert "estado" in repetida.data


@pytest.mark.django_db(transaction=True)
def test_detalle_invalido_sigue_siendo_400_y_no_conflicto(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="fe04-validacion"))
    proforma = crear_proforma(
        actor=actor,
        cliente=cliente_persona(actor),
    )

    producto = silla(
        actor,
        sku=f"FE04-VALIDACION-{proforma.id}",
        precio="100.00",
    )

    api = APIClient()
    api.force_authenticate(actor)
    respuesta = api.post(
        f"/api/v1/proformas/{proforma.id}/detalles/",
        {
            "tipo_item": valor("TIPO_ITEM", "SILLA").id,
            "producto": producto.id,
            "nombre": "Inválido",
            "cantidad": 1,
            "unidad": valor("UNIDAD_MEDIDA", "PIEZA").id,
            "modo_calculo": "TOTAL_NEGOCIADO",
            "precio_unitario": "0.00",
            "descuento": "0.00",
        },
        format="json",
    )

    assert respuesta.status_code == 400
