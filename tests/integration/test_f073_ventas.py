from decimal import Decimal

import pytest
from django.db import DatabaseError
from rest_framework.exceptions import ValidationError

from apps.movimientos_stock.models import MovimientoStock
from apps.ordenes_trabajo.models import OrdenTrabajo
from apps.pedidos.models import Pedido
from apps.pedidos.services import aprobar_proforma, cancelar_pedido
from apps.proformas.services import agregar_detalle, crear_proforma, enviar_proforma
from tests.factories import cargar_stock, cliente_persona, silla, valor


def proforma_enviada(actor, producto, cantidad=1):
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "SILLA"),
        producto_id=producto.id,
        nombre=producto.nombre,
        cantidad=cantidad,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("50.00"),
    )
    return enviar_proforma(proforma_id=proforma.id, actor=actor), detalle


@pytest.mark.django_db(transaction=True)
def test_aprobacion_crea_pedido_venta_ot_y_descuenta_stock(django_user_model):
    actor = django_user_model.objects.create_user(username="venta-ok")
    producto = silla(actor, sku="VENTA-OK")
    cargar_stock(producto, actor, 3)
    proforma, _ = proforma_enviada(actor, producto, 2)
    pedido = aprobar_proforma(proforma_id=proforma.id, actor=actor)
    producto.refresh_from_db()
    assert Pedido.objects.filter(proforma=proforma).count() == 1
    assert OrdenTrabajo.objects.filter(pedido=pedido).count() == 1
    assert producto.stock == 1
    assert MovimientoStock.objects.filter(pedido=pedido, cantidad=-2).count() == 1


@pytest.mark.django_db(transaction=True)
def test_stock_insuficiente_revierte_aprobacion_completa(django_user_model):
    actor = django_user_model.objects.create_user(username="venta-sin-stock")
    producto = silla(actor, sku="VENTA-SIN-STOCK")
    cargar_stock(producto, actor, 1)
    proforma, _ = proforma_enviada(actor, producto, 2)
    with pytest.raises(DatabaseError):
        aprobar_proforma(proforma_id=proforma.id, actor=actor)
    proforma.refresh_from_db()
    producto.refresh_from_db()
    assert proforma.estado.codigo == "ENVIADA"
    assert not Pedido.objects.filter(proforma=proforma).exists()
    assert producto.stock == 1


@pytest.mark.django_db(transaction=True)
def test_cancelacion_genera_una_reversa_y_restituye_stock(django_user_model):
    actor = django_user_model.objects.create_user(username="venta-cancelar")
    producto = silla(actor, sku="VENTA-CANCELAR")
    cargar_stock(producto, actor, 1)
    proforma, _ = proforma_enviada(actor, producto)
    pedido = aprobar_proforma(proforma_id=proforma.id, actor=actor)
    cancelar_pedido(pedido_id=pedido.id, actor=actor)
    producto.refresh_from_db()
    assert producto.stock == 1
    assert MovimientoStock.objects.filter(movimiento_referencia__isnull=False).count() == 1
    with pytest.raises(ValidationError):
        cancelar_pedido(pedido_id=pedido.id, actor=actor)


@pytest.mark.concurrency
@pytest.mark.django_db(transaction=True)
def test_dos_aprobaciones_compiten_por_ultima_unidad(django_user_model):
    actor_uno = django_user_model.objects.create_user(username="competidor-uno")
    actor_dos = django_user_model.objects.create_user(username="competidor-dos")
    producto = silla(actor_uno, sku="ULTIMA-UNIDAD")
    cargar_stock(producto, actor_uno, 1)
    primera, _ = proforma_enviada(actor_uno, producto)
    segunda, _ = proforma_enviada(actor_dos, producto)
    aprobar_proforma(proforma_id=primera.id, actor=actor_uno)
    with pytest.raises(DatabaseError):
        aprobar_proforma(proforma_id=segunda.id, actor=actor_dos)
    producto.refresh_from_db()
    primera.refresh_from_db()
    segunda.refresh_from_db()
    assert producto.stock == 0
    assert Pedido.objects.filter(proforma__in=[primera, segunda]).count() == 1
    assert primera.estado.codigo == "APROBADA"
    assert segunda.estado.codigo == "ENVIADA"
