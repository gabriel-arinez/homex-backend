"""Regresiones de AP5: revisión, valores históricos, decimales y PDF extenso."""

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.catalogo.models import DescuentoProducto, Producto, ValorCatalogo
from apps.catalogo.revision import revision_producto
from apps.documentos.pdf import renderizar_proforma_pdf
from apps.proformas.models import EspecificacionMueble
from apps.proformas.services import agregar_detalle, crear_proforma, enviar_proforma
from tests.api.test_ap5_catalogo_documentos import payload
from tests.factories import cliente_persona, valor, vendedor


@pytest.mark.django_db(transaction=True)
def test_revisiones_obsoletas_no_sobrescriben_productos_ni_promociones(django_user_model):
    admin = django_user_model.objects.create_user(username="ap5-version", is_staff=True)
    api = APIClient()
    api.force_authenticate(admin)
    creado = api.post(
        "/api/v1/catalogo/productos/",
        payload(
            "OTRO",
            "JUEGO",
            "AP5-VERSION",
            promocion={"precio_antes": "100.00", "precio_ahora": "80.00", "activo": False},
        ),
        format="json",
    )
    assert creado.status_code == 201, creado.data
    pk = creado.data["id"]
    rev = creado.data["revision"]
    assert len(rev) == 64
    url = f"/api/v1/catalogo/productos/{pk}/"
    assert api.patch(url, {"nombre": "Sin precondición"}, format="json").status_code == 400
    guardado = api.patch(
        url, {"nombre": "Guardado por administrador A"}, format="json", HTTP_IF_MATCH=rev
    )
    assert guardado.status_code == 200, guardado.data
    assert guardado.data["revision"] != rev
    conflicto = api.patch(
        url,
        {"nombre": "Modificación obsoleta", "promocion": {"activo": True}},
        format="json",
        HTTP_IF_MATCH=rev,
    )
    assert conflicto.status_code == 409, conflicto.data
    actual = Producto.objects.get(pk=pk)
    assert actual.nombre == "Guardado por administrador A"
    assert DescuentoProducto.objects.get(producto=actual).activo is False


@pytest.mark.django_db(transaction=True)
def test_json_catalogo_expone_decimales_como_cadenas(django_user_model):
    admin = django_user_model.objects.create_user(username="ap5-decimal", is_staff=True)
    api = APIClient()
    api.force_authenticate(admin)
    creado = api.post(
        "/api/v1/catalogo/productos/",
        payload("OTRO", "PIEZA", "AP5-DEC"),
        format="json",
    )
    assert creado.status_code == 201, creado.data
    respuesta = api.get(f"/api/v1/catalogo/productos/{creado.data['id']}/")
    assert respuesta.status_code == 200
    datos = respuesta.json()
    for campo in ("precio_vigente", "demanda_pendiente", "disponibilidad_referencial"):
        assert isinstance(datos[campo], str), (campo, datos[campo])
    assert Decimal(datos["precio_vigente"]) == Decimal("100.00")


@pytest.mark.django_db(transaction=True)
def test_catalogo_inactivo_historico_no_impide_corregir_precio(django_user_model):
    admin = django_user_model.objects.create_user(username="ap5-historico", is_staff=True)
    api = APIClient()
    api.force_authenticate(admin)
    creado = api.post(
        "/api/v1/catalogo/productos/",
        payload("OTRO", "PIEZA", "AP5-OLD"),
        format="json",
    )
    assert creado.status_code == 201, creado.data
    producto = Producto.objects.get(pk=creado.data["id"])
    ValorCatalogo.objects.filter(pk__in=[producto.categoria_id, producto.unidad_stock_id]).update(
        activo=False
    )
    actualizado = api.patch(
        f"/api/v1/catalogo/productos/{producto.pk}/",
        {"nombre": "Producto histórico", "precio_lista": "110.00"},
        format="json",
        HTTP_IF_MATCH=revision_producto(producto),
    )
    assert actualizado.status_code == 200, actualizado.data
    assert actualizado.data["precio_lista"] == "110.00"


@pytest.mark.django_db(transaction=True)
def test_pdf_admite_una_linea_y_una_ficha_de_varias_paginas(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap5-pdf-largo"))
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    detalle = agregar_detalle(
        proforma_id=proforma.pk,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
        nombre="Mesa con descripción extensa",
        descripcion="Descripción detallada " * 1100,
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("100.00"),
        descuento=Decimal("0.00"),
    )
    EspecificacionMueble.objects.create(
        proforma_detalle=detalle,
        datos_tecnicos={"componentes": [{"nombre": "parte", "detalle": "Melamina " * 1400}]},
    )
    enviar_proforma(proforma_id=proforma.pk, actor=actor)
    documento = renderizar_proforma_pdf(proforma.pk)
    assert documento.startswith(b"%PDF")
    assert documento.count(b"/Type /Page") >= 2
