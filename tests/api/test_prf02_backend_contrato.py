from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.catalogo.models import (
    ConceptoCatalogo,
    FamiliaProducto,
    Producto,
    ProductoPiso,
    ProductoSilla,
    ValorCatalogo,
)
from apps.documentos.pdf import _descripcion_linea
from apps.proformas.models import DetalleProforma
from apps.proformas.services import agregar_detalle, crear_proforma, enviar_proforma
from tests.factories import cliente_persona, valor, vendedor


def opcion(concepto, codigo, *, activo=True):
    concepto_obj, _ = ConceptoCatalogo.objects.get_or_create(codigo=concepto)
    objeto, _ = ValorCatalogo.objects.get_or_create(
        concepto=concepto_obj,
        codigo=codigo,
        defaults={"nombre": codigo.replace("_", " ").title(), "activo": activo},
    )
    if objeto.activo != activo:
        objeto.activo = activo
        objeto.save(update_fields=["activo"])
    return objeto


def producto(actor, categoria, unidad, sku, familia=None):
    return Producto.objects.create(
        categoria=valor("CATEGORIA_PRODUCTO", categoria),
        familia=familia,
        sku=sku,
        nombre=sku,
        precio_lista=Decimal("100.00"),
        stock=Decimal("0.0000"),
        unidad_stock=valor("UNIDAD_MEDIDA", unidad),
        created_by=actor,
        updated_by=actor,
    )


@pytest.mark.django_db(transaction=True)
def test_filtros_sql_por_ficha_familia_y_opciones_historicas(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="prf02-filtros"))
    familia = FamiliaProducto.objects.create(codigo="PRF02-F", nombre="Familia PRF02")
    marca = opcion("MARCA", "PRF02-MARCA")
    color = opcion("COLOR", "PRF02-COLOR")
    silla = producto(actor, "SILLA", "PIEZA", "PRF02-SILLA", familia)
    ProductoSilla.objects.create(
        producto=silla, marca=marca, modelo="Ejecutiva B15", color_primario=color
    )
    piso = producto(actor, "PISO_FLOTANTE", "M2", "PRF02-PISO", familia)
    tipo = opcion("TIPO_PISO", "LAMINADO")
    material = opcion("MATERIAL_PISO", "HDF")
    diseno = opcion("DISENO_PISO", "ROBLE")
    acabado = opcion("ACABADO_PISO", "MATE")
    ProductoPiso.objects.create(
        producto=piso,
        marca=marca,
        tipo=tipo,
        material=material,
        diseno=diseno,
        acabado=acabado,
        espesor_mm=Decimal("8.00"),
    )
    marca.activo = False
    marca.save(update_fields=["activo"])
    otro = producto(actor, "OTRO", "BARRA", "PRF02-ZOCALO", familia)
    api = APIClient()
    api.force_authenticate(actor)

    casos = [
        ({"categoria": silla.categoria_id, "marca": marca.id}, silla.id),
        ({"categoria": silla.categoria_id, "modelo": "b15"}, silla.id),
        ({"categoria": silla.categoria_id, "color_primario": color.id}, silla.id),
        ({"categoria": piso.categoria_id, "tipo": tipo.id}, piso.id),
        ({"categoria": piso.categoria_id, "material": material.id}, piso.id),
        ({"categoria": piso.categoria_id, "diseno": diseno.id}, piso.id),
        ({"categoria": piso.categoria_id, "acabado": acabado.id}, piso.id),
        ({"categoria": piso.categoria_id, "espesor_mm": "8.00"}, piso.id),
        ({"categoria": otro.categoria_id, "unidad_stock": otro.unidad_stock_id}, otro.id),
        ({"familia": familia.id, "search": "PRF02-ZOCALO"}, otro.id),
    ]
    for parametros, esperado in casos:
        respuesta = api.get("/api/v1/catalogo/productos/", parametros)
        assert respuesta.status_code == 200, respuesta.data
        assert [fila["id"] for fila in respuesta.data["results"]] == [esperado]


@pytest.mark.django_db(transaction=True)
def test_filtros_rechazan_ids_y_combinaciones_incompatibles(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="prf02-validacion"))
    api = APIClient()
    api.force_authenticate(actor)
    silla = valor("CATEGORIA_PRODUCTO", "SILLA")
    color = opcion("COLOR", "PRF02-COLOR-INVALIDO")

    casos = [
        {"categoria": 999999},
        {"familia": 999999},
        {"marca": color.id},
        {"categoria": silla.id, "material": color.id},
        {"categoria": silla.id, "unidad_stock": valor("UNIDAD_MEDIDA", "PIEZA").id},
        {"categoria": silla.id, "espesor_mm": "0"},
    ]
    for parametros in casos:
        assert api.get("/api/v1/catalogo/productos/", parametros).status_code == 400


@pytest.mark.django_db(transaction=True)
def test_listado_no_crece_en_consultas_por_demanda(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="prf02-consultas"))
    api = APIClient()
    api.force_authenticate(actor)
    for indice in range(8):
        producto(actor, "OTRO", "PIEZA", f"PRF02-Q-{indice}")

    with CaptureQueriesContext(connection) as una:
        assert api.get("/api/v1/catalogo/productos/", {"page_size": 1}).status_code == 200
    with CaptureQueriesContext(connection) as ocho:
        assert api.get("/api/v1/catalogo/productos/", {"page_size": 8}).status_code == 200
    assert len(ocho) <= len(una) + 1


@pytest.mark.django_db(transaction=True)
def test_resolver_variante_pendiente_conserva_linea_y_valores_negociados(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="prf02-resolver"))
    familia = FamiliaProducto.objects.create(codigo="PRF02-PEND", nombre="Pendiente")
    variante = producto(actor, "SILLA", "PIEZA", "PRF02-VARIANTE", familia)
    ProductoSilla.objects.create(producto=variante)
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "SILLA"),
        producto=None,
        familia_producto=familia,
        nombre="Silla por seleccionar",
        cantidad=Decimal("2"),
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("87.50"),
        descuento=Decimal("5.00"),
    )
    enviar_proforma(proforma_id=proforma.id, actor=actor)
    api = APIClient()
    api.force_authenticate(actor)
    respuesta = api.patch(
        f"/api/v1/proformas-detalle/{detalle.id}/",
        {"producto": variante.id},
        format="json",
    )
    assert respuesta.status_code == 200, respuesta.data
    detalle.refresh_from_db()
    assert detalle.id == respuesta.data["id"]
    assert detalle.producto_id == variante.id
    assert detalle.familia_producto_id == familia.id
    assert detalle.precio_unitario == Decimal("87.50")
    assert detalle.descuento == Decimal("5.00")
    assert detalle.total == Decimal("170.00")


@pytest.mark.django_db(transaction=True)
def test_resolver_variante_incompatible_devuelve_400_y_no_modifica(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="prf02-incompatible"))
    familia = FamiliaProducto.objects.create(codigo="PRF02-INC", nombre="Incompatible")
    variante = producto(actor, "OTRO", "PIEZA", "PRF02-OTRA", familia)
    proforma = crear_proforma(actor=actor)
    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "SILLA"),
        familia_producto=familia,
        nombre="Silla pendiente",
        cantidad=Decimal("1"),
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("50.00"),
    )
    api = APIClient()
    api.force_authenticate(actor)
    respuesta = api.patch(
        f"/api/v1/proformas-detalle/{detalle.id}/",
        {"producto": variante.id},
        format="json",
    )
    assert respuesta.status_code == 400
    detalle.refresh_from_db()
    assert detalle.producto_id is None


@pytest.mark.django_db(transaction=True)
def test_pdf_identifica_variante_pendiente_sin_promesa_de_stock(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="prf02-pdf"))
    familia = FamiliaProducto.objects.create(codigo="PRF02-PDF", nombre="Pendiente PDF")
    proforma = crear_proforma(actor=actor)
    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "OTRO"),
        familia_producto=familia,
        nombre="Producto por definir",
        cantidad=Decimal("1"),
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("10.00"),
    )
    texto = _descripcion_linea(DetalleProforma.objects.get(pk=detalle.pk))
    assert "Variante pendiente de selección" in texto
    assert "sin SKU definitivo ni stock reservado" in texto
