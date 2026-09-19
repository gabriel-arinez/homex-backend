import pytest
from django.db import DatabaseError, transaction

from apps.notas_entrega.services import emitir_nota
from apps.pedidos.services import aprobar_proforma
from apps.recibos.models import Recibo
from apps.recibos.services import anular_recibo, emitir_recibo
from tests.factories import cargar_stock, silla, valor
from tests.integration.test_f073_ventas import proforma_enviada


@pytest.mark.django_db(transaction=True)
def test_recibo_anulable_e_inmutable_y_sobrepago_rechazado(django_user_model):
    actor = django_user_model.objects.create_user(username="cobro")
    producto = silla(actor, sku="COBRO")
    cargar_stock(producto, actor, 1)
    proforma, _ = proforma_enviada(actor, producto)
    pedido = aprobar_proforma(proforma_id=proforma.id, actor=actor)
    recibo = emitir_recibo(
        pedido=pedido,
        actor=actor,
        nombre_completo="Ana",
        monto_en_letras="cincuenta",
        concepto="Anticipo",
        tipo_pago=valor("TIPO_PAGO", "EFECTIVO"),
        pago_actual=50,
    )
    assert recibo.estado == "EMITIDO" and recibo.saldo == 0
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            Recibo.objects.filter(pk=recibo.id).update(concepto="alterado")
    anular_recibo(recibo_id=recibo.id, actor=actor)
    recibo.refresh_from_db()
    assert recibo.estado == "ANULADO"
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            Recibo.objects.filter(pk=recibo.id).delete()


@pytest.mark.django_db(transaction=True)
def test_nota_solo_listo_entrega(django_user_model):
    actor = django_user_model.objects.create_user(username="nota")
    producto = silla(actor, sku="NOTA")
    cargar_stock(producto, actor, 1)
    proforma, _ = proforma_enviada(actor, producto)
    pedido = aprobar_proforma(proforma_id=proforma.id, actor=actor)
    with pytest.raises(DatabaseError):
        emitir_nota(pedido=pedido, actor=actor)


@pytest.mark.django_db(transaction=True)
def test_recibo_emitido_bloquea_cancelacion_y_anulado_no(django_user_model):
    from apps.pedidos.services import cancelar_pedido

    actor = django_user_model.objects.create_user(username="cancelacion-cobro")
    producto = silla(actor, sku="CANCELACION-COBRO")
    cargar_stock(producto, actor, 1)
    proforma, _ = proforma_enviada(actor, producto)
    pedido = aprobar_proforma(proforma_id=proforma.id, actor=actor)
    recibo = emitir_recibo(
        pedido=pedido,
        actor=actor,
        nombre_completo="Ana",
        monto_en_letras="cincuenta",
        concepto="Anticipo",
        tipo_pago=valor("TIPO_PAGO", "EFECTIVO"),
        pago_actual=50,
    )
    with pytest.raises(Exception):
        cancelar_pedido(pedido_id=pedido.id, actor=actor)
    anular_recibo(recibo_id=recibo.id, actor=actor)
    assert cancelar_pedido(pedido_id=pedido.id, actor=actor).estado.codigo == "CANCELADO"


@pytest.mark.django_db(transaction=True)
def test_documentos_renderizan_datos_persistidos(django_user_model):
    from apps.documentos.services import (
        renderizar_nota_entrega,
        renderizar_orden_trabajo,
        renderizar_proforma,
        renderizar_recibo,
    )
    from apps.ordenes_trabajo.models import OrdenTrabajo

    actor = django_user_model.objects.create_user(username="documentos")
    producto = silla(actor, sku="DOCUMENTOS")
    cargar_stock(producto, actor, 1)
    proforma, _ = proforma_enviada(actor, producto)
    pedido = aprobar_proforma(proforma_id=proforma.id, actor=actor)
    recibo = emitir_recibo(
        pedido=pedido,
        actor=actor,
        nombre_completo="Ana",
        monto_en_letras="cincuenta",
        concepto="Anticipo",
        tipo_pago=valor("TIPO_PAGO", "EFECTIVO"),
        pago_actual=50,
    )
    pedido.estado = valor("ESTADO_PEDIDO", "EN_PRODUCCION")
    pedido.save(update_fields=["estado"])
    pedido.estado = valor("ESTADO_PEDIDO", "LISTO_ENTREGA")
    pedido.save(update_fields=["estado"])
    nota = emitir_nota(pedido=pedido, actor=actor)
    orden = OrdenTrabajo.objects.get(pedido=pedido)

    assert str(proforma.numero) in renderizar_proforma(proforma.id)
    assert str(orden.numero) in renderizar_orden_trabajo(orden.id)
    assert str(recibo.numero) in renderizar_recibo(recibo.id)
    assert str(nota.numero) in renderizar_nota_entrega(nota.id)
