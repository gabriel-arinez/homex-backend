from decimal import Decimal

import pytest

from apps.notas_entrega.models import NotaEntrega
from apps.notas_entrega.services import emitir_nota
from apps.ordenes_trabajo.models import OrdenTrabajo
from apps.pedidos.services import aprobar_proforma, cancelar_pedido
from apps.proformas.services import agregar_detalle, crear_proforma, enviar_proforma
from apps.recibos.models import Recibo
from apps.recibos.services import emitir_recibo
from tests.factories import cargar_stock, cliente_persona, silla, valor, vendedor


@pytest.mark.django_db(transaction=True)
def test_recorrido_comercial_e2e_y_cancelacion_sin_cobro(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="e2e-vendedor"))
    producto = silla(actor, sku="E2E-SILLA", precio="50.00")
    cargar_stock(producto, actor, 2)

    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "SILLA"),
        producto_id=producto.id,
        nombre=producto.nombre,
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("50.00"),
    )
    proforma = enviar_proforma(proforma_id=proforma.id, actor=actor)
    pedido = aprobar_proforma(proforma_id=proforma.id, actor=actor)
    assert OrdenTrabajo.objects.filter(pedido=pedido).exists()

    recibo = emitir_recibo(
        pedido=pedido,
        actor=actor,
        nombre_completo="Ana López",
        monto_en_letras="cincuenta",
        concepto="Pago",
        tipo_pago=valor("TIPO_PAGO", "EFECTIVO"),
        pago_actual=Decimal("50.00"),
    )
    assert Recibo.objects.filter(pk=recibo.id, estado="EMITIDO").exists()
    pedido.estado = valor("ESTADO_PEDIDO", "EN_PRODUCCION")
    pedido.save(update_fields=["estado"])
    pedido.estado = valor("ESTADO_PEDIDO", "LISTO_ENTREGA")
    pedido.save(update_fields=["estado"])
    assert NotaEntrega.objects.filter(pk=emitir_nota(pedido=pedido, actor=actor).id).exists()

    otro = silla(actor, sku="E2E-CANCELAR", precio="20.00")
    cargar_stock(otro, actor, 1)
    proforma_cancelable = crear_proforma(actor=actor, cliente=cliente_persona(actor, sufijo="2"))
    agregar_detalle(
        proforma_id=proforma_cancelable.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "SILLA"),
        producto_id=otro.id,
        nombre=otro.nombre,
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("20.00"),
    )
    enviar_proforma(proforma_id=proforma_cancelable.id, actor=actor)
    pedido_cancelable = aprobar_proforma(proforma_id=proforma_cancelable.id, actor=actor)
    assert cancelar_pedido(pedido_id=pedido_cancelable.id, actor=actor).estado.codigo == "CANCELADO"
