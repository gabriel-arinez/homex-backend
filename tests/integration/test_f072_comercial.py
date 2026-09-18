from decimal import Decimal

import pytest
from django.db import DatabaseError, transaction

from apps.catalogo.models import DescuentoProducto
from apps.proformas.models import DetalleProforma, EspecificacionMueble
from apps.proformas.services import agregar_detalle, crear_proforma, enviar_proforma
from tests.factories import cliente_persona, silla, valor


def nueva_proforma(actor, *, cliente=None):
    return crear_proforma(actor=actor, cliente=cliente)


@pytest.mark.django_db(transaction=True)
def test_total_negociado_preserva_el_importe_exacto(django_user_model):
    actor = django_user_model.objects.create_user(username="vendedor-total")
    proforma = nueva_proforma(actor)
    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
        nombre="Mueble",
        cantidad=3,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        modo_calculo="TOTAL_NEGOCIADO",
        precio_unitario=Decimal("33.33"),
        importe_negociado=Decimal("100.00"),
        descuento=Decimal("0.00"),
    )
    detalle.refresh_from_db()
    proforma.refresh_from_db()
    assert detalle.total == Decimal("100.00")
    assert proforma.total == Decimal("100.00")


@pytest.mark.django_db(transaction=True)
def test_precio_unitario_descuenta_y_totales_no_son_editables(django_user_model):
    actor = django_user_model.objects.create_user(username="vendedor-precio")
    proforma = nueva_proforma(actor)
    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
        nombre="Mueble",
        cantidad=2,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("50.00"),
        descuento=Decimal("5.00"),
    )
    detalle.refresh_from_db()
    proforma.refresh_from_db()
    assert detalle.total == Decimal("95.00")
    assert proforma.subtotal == Decimal("100.00")
    assert proforma.descuento_total == Decimal("5.00")
    assert proforma.total == Decimal("95.00")
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            Proforma = type(proforma)
            Proforma.objects.filter(pk=proforma.id).update(total=Decimal("1.00"))


@pytest.mark.django_db(transaction=True)
def test_modo_invalido_es_rechazado_por_base_de_datos(django_user_model):
    actor = django_user_model.objects.create_user(username="vendedor-modo")
    proforma = nueva_proforma(actor)
    with pytest.raises(DatabaseError):
        DetalleProforma.objects.create(
            proforma=proforma,
            tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
            nombre="X",
            cantidad=1,
            unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
            modo_calculo="INVALIDO",
            precio_unitario=Decimal("1.00"),
        )


@pytest.mark.django_db(transaction=True)
def test_envio_congela_cliente_y_snapshots(django_user_model):
    actor = django_user_model.objects.create_user(username="vendedor-snapshot")
    cliente = cliente_persona(actor)
    proforma = nueva_proforma(actor, cliente=cliente)
    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
        nombre="Mueble",
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("50.00"),
    )
    EspecificacionMueble.objects.create(proforma_detalle=detalle, dimensiones={"ancho": "1 m"})
    enviada = enviar_proforma(proforma_id=proforma.id, actor=actor)
    assert enviada.estado.codigo == "ENVIADA"
    assert enviada.cliente_nombre_snapshot == "Ana López"
    otro_cliente = cliente_persona(actor, sufijo=" Dos")
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            type(enviada).objects.filter(pk=enviada.id).update(cliente=otro_cliente)


@pytest.mark.django_db(transaction=True)
def test_detalle_no_puede_migrar_a_otra_proforma(django_user_model):
    actor = django_user_model.objects.create_user(username="vendedor-detalle")
    proforma = nueva_proforma(actor)
    otra = nueva_proforma(actor)
    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
        nombre="Mueble",
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("50.00"),
    )
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            DetalleProforma.objects.filter(pk=detalle.id).update(proforma=otra)


@pytest.mark.django_db(transaction=True)
def test_promocion_bob_se_aplica_automaticamente(django_user_model):
    actor = django_user_model.objects.create_user(username="vendedor-promo")
    producto = silla(actor, sku="PROMO", precio="50.00")
    DescuentoProducto.objects.create(producto=producto, precio_antes="50.00", precio_ahora="40.00")
    proforma = nueva_proforma(actor)
    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "SILLA"),
        producto_id=producto.id,
        nombre=producto.nombre,
        cantidad=2,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("999.00"),
    )
    detalle.refresh_from_db()
    assert detalle.precio_unitario == Decimal("40.00")
    assert detalle.precio_antes_snapshot == Decimal("50.00")
    assert detalle.precio_ahora_snapshot == Decimal("40.00")
    assert detalle.total == Decimal("80.00")
