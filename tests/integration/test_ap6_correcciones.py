"""Regresiones AP6: unidad de venta/stock, céntimos, ficha V2 y acceso OT."""

from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.db import DatabaseError, transaction
from rest_framework.test import APIClient

from apps.catalogo.models import Producto, ProductoPiso
from apps.pedidos.services import aprobar_proforma
from apps.proformas.api.serializers import EspecificacionMuebleSerializer
from apps.proformas.models import DetalleProforma, EspecificacionMueble
from apps.proformas.services import agregar_detalle, crear_proforma, enviar_proforma
from tests.factories import cargar_stock, cliente_persona, valor, vendedor


def producto_de_catalogo(actor, *, sku, categoria="OTRO", unidad="BARRA", stock="5"):
    producto = Producto.objects.create(
        categoria=valor("CATEGORIA_PRODUCTO", categoria),
        sku=sku,
        nombre=sku,
        precio_lista=Decimal("0.01"),
        unidad_stock=valor("UNIDAD_MEDIDA", unidad),
        stock=0,
        created_by=actor,
        updated_by=actor,
    )
    if categoria == "PISO_FLOTANTE":
        ProductoPiso.objects.create(producto=producto, created_by=actor, updated_by=actor)
    cargar_stock(producto, actor, Decimal(stock))
    return producto


@pytest.mark.django_db(transaction=True)
def test_ap6_unidad_linea_debe_coincidir_exactamente_con_stock(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap6-unidad-stock"))
    barra = producto_de_catalogo(actor, sku="AP6-ZOCALO-BARRA")
    proforma = crear_proforma(actor=actor)

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            agregar_detalle(
                proforma_id=proforma.id,
                actor=actor,
                tipo_item=valor("TIPO_ITEM", "OTRO"),
                producto=barra,
                nombre="Zócalo",
                cantidad=1,
                unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
                precio_unitario=Decimal("3.00"),
            )
    assert not DetalleProforma.objects.filter(proforma=proforma).exists()
    barra.refresh_from_db()
    assert barra.stock == Decimal("5.0000")

    compatible = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "OTRO"),
        producto=barra,
        nombre="Zócalo",
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "BARRA"),
        precio_unitario=Decimal("3.00"),
    )
    assert compatible.id is not None


@pytest.mark.django_db(transaction=True)
def test_ap6_unidad_producto_no_puede_reinterpretar_stock_o_cotizaciones(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap6-congelar-unidad"))
    barra = producto_de_catalogo(actor, sku="AP6-ZOCALO-UNIDAD-HISTORICA")
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            Producto.objects.filter(pk=barra.pk).update(
                unidad_stock=valor("UNIDAD_MEDIDA", "PIEZA")
            )
    barra.refresh_from_db()
    assert barra.unidad_stock.codigo == "BARRA"
    assert barra.stock == Decimal("5.0000")

    sin_movimientos = Producto.objects.create(
        categoria=valor("CATEGORIA_PRODUCTO", "OTRO"),
        sku="AP6-SIN-STOCK-CAMBIO-VALIDO",
        nombre="Sin movimientos",
        unidad_stock=valor("UNIDAD_MEDIDA", "BARRA"),
        stock=0,
        created_by=actor,
        updated_by=actor,
    )
    # HOMEX ya protegía unidad_stock de manera incondicional, incluso
    # en artículos aún sin movimientos ni cotizaciones.
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            Producto.objects.filter(pk=sin_movimientos.pk).update(
                unidad_stock=valor("UNIDAD_MEDIDA", "PIEZA")
            )
    sin_movimientos.refresh_from_db()
    assert sin_movimientos.unidad_stock.codigo == "BARRA"

    proforma = crear_proforma(actor=actor)
    agregar_detalle(
        proforma_id=proforma.pk,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "OTRO"),
        producto=sin_movimientos,
        nombre="Cotización de referencia",
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "BARRA"),
        precio_unitario=Decimal("10.00"),
    )
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            Producto.objects.filter(pk=sin_movimientos.pk).update(
                unidad_stock=valor("UNIDAD_MEDIDA", "PIEZA")
            )
    sin_movimientos.refresh_from_db()
    assert sin_movimientos.unidad_stock.codigo == "BARRA"


@pytest.mark.django_db(transaction=True)
def test_ap6_subtotal_suma_brutos_redondeados_por_linea(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap6-centimos"))
    proforma = crear_proforma(actor=actor)
    for n in (1, 2):
        piso = producto_de_catalogo(
            actor, sku=f"AP6-CENTIMOS-{n}", categoria="PISO_FLOTANTE", unidad="M2"
        )
        detalle = agregar_detalle(
            proforma_id=proforma.id,
            actor=actor,
            tipo_item=valor("TIPO_ITEM", "PISO_FLOTANTE"),
            producto=piso,
            nombre=piso.nombre,
            cantidad=Decimal("0.5000"),
            unidad=valor("UNIDAD_MEDIDA", "M2"),
            precio_unitario=Decimal("0.01"),
        )
        detalle.refresh_from_db()
        assert detalle.total == Decimal("0.01")

    proforma.refresh_from_db()
    assert proforma.subtotal == Decimal("0.02")
    assert proforma.descuento_total == Decimal("0.00")
    assert proforma.total == Decimal("0.02")

    # Ninguna escritura directa de un total altera el importe comercial.
    DetalleProforma.objects.filter(pk=detalle.pk).update(total=Decimal("999.00"))
    detalle.refresh_from_db()
    proforma.refresh_from_db()
    assert detalle.total == Decimal("0.01")
    assert proforma.total == Decimal("0.02")


@pytest.mark.django_db(transaction=True)
def test_ap6_ot_unica_imprime_ambos_items_y_solo_jefe_ve_ficha(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap6-ot-actor"))
    producto = producto_de_catalogo(
        actor, sku="AP6-OT-CATALOGO", categoria="PISO_FLOTANTE", unidad="M2"
    )
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "PISO_FLOTANTE"),
        producto=producto,
        nombre="Piso de catálogo",
        descripcion="Dato de catálogo confidencial para taller",
        cantidad=Decimal("1.5000"),
        unidad=valor("UNIDAD_MEDIDA", "M2"),
        precio_unitario=Decimal("30.00"),
    )
    mueble = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
        nombre="Escritorio especial",
        descripcion="Preparar mesón y estructura",
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("500.00"),
    )
    EspecificacionMueble.objects.create(
        proforma_detalle=mueble,
        componentes=[
            {"nombre": "Mesón", "material": "Melamina", "color": "Nogal"},
            {"nombre": "Estructura", "espesor": "18 mm", "color": "Blanco"},
        ],
        texto_original="Escritorio nogal a elección",
    )
    enviar_proforma(proforma_id=proforma.id, actor=actor)
    pedido = aprobar_proforma(proforma_id=proforma.id, actor=actor)
    url = f"/api/v1/ordenes-trabajo/{pedido.ordentrabajo.id}/"

    vendedor_api = APIClient()
    vendedor_api.force_authenticate(actor)
    vendedor_resultado = vendedor_api.get(url)
    assert vendedor_resultado.status_code == 200
    assert len(vendedor_resultado.data["detalles"]) == 2
    assert all(item["especificacion"] is None for item in vendedor_resultado.data["detalles"])
    documento_vendedor = vendedor_api.get(url + "documento/")
    assert documento_vendedor.status_code == 200
    assert b"Piso de cat" in documento_vendedor.content
    assert b"Escritorio especial" in documento_vendedor.content
    assert b"Nogal" not in documento_vendedor.content
    assert b"confidencial" not in documento_vendedor.content

    jefe = django_user_model.objects.create_user(username="ap6-ot-jefe")
    grupo, _ = Group.objects.get_or_create(name="JEFE_TALLER")
    jefe.groups.add(grupo)
    jefe_api = APIClient()
    jefe_api.force_authenticate(jefe)
    resultado = jefe_api.get(url)
    assert resultado.status_code == 200
    catalogo, personalizado = resultado.data["detalles"]
    assert catalogo["especificacion"] is None
    assert catalogo["descripcion"] is None
    assert personalizado["especificacion"]["componentes"][0]["color"] == "Nogal"
    assert "precio_unitario" not in personalizado and "total" not in personalizado

    documento_jefe = jefe_api.get(url + "documento/")
    assert documento_jefe.status_code == 200
    assert b"Nogal" in documento_jefe.content
    assert b"Escritorio especial" in documento_jefe.content
    assert b"confidencial" not in documento_jefe.content


@pytest.mark.django_db
def test_ap6_serializer_rechaza_componentes_malformados_y_advertencias_invalidas():
    comunes = {"schema_version": 2, "componentes": [{"nombre": "Mesón"}]}
    assert not EspecificacionMuebleSerializer(
        data={**comunes, "componentes": [{"color": "Nogal"}]}
    ).is_valid()
    assert not EspecificacionMuebleSerializer(data={**comunes, "componentes": []}).is_valid()
    assert not EspecificacionMuebleSerializer(data={**comunes, "advertencias": [""]}).is_valid()
    valido = EspecificacionMuebleSerializer(
        data={
            **comunes,
            "texto_original": "Mesa color a elección",
            "advertencias": ["color_pendiente"],
            "componentes": [
                {"nombre": "Mesón", "espesor": "25 mm", "color": "Nogal"},
                {"nombre": "Estructura", "dimensiones": {"alto": "75 cm"}},
            ],
        }
    )
    assert valido.is_valid(), valido.errors
