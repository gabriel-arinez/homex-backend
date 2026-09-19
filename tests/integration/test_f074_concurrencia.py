from decimal import Decimal

import pytest

from apps.notas_entrega.models import NotaEntrega
from apps.notas_entrega.services import emitir_nota
from apps.pedidos.services import aprobar_proforma
from apps.recibos.models import Recibo
from apps.recibos.services import emitir_recibo
from tests.factories import cargar_stock, silla, valor
from tests.integration.test_f073_ventas import ejecutar_en_paralelo, proforma_enviada


@pytest.mark.concurrency
@pytest.mark.django_db(transaction=True)
def test_cobros_concurrentes_no_superan_el_saldo(django_user_model):
    actor = django_user_model.objects.create_user(username="cobros-concurrentes")
    producto = silla(actor, sku="COBROS-CONCURRENTES")
    cargar_stock(producto, actor, 1)
    proforma, _ = proforma_enviada(actor, producto)
    pedido = aprobar_proforma(proforma_id=proforma.id, actor=actor)
    tipo_pago = valor("TIPO_PAGO", "EFECTIVO")

    def cobrar(nombre):
        return emitir_recibo(
            pedido=pedido,
            actor=actor,
            nombre_completo=nombre,
            monto_en_letras="treinta",
            concepto="Anticipo",
            tipo_pago=tipo_pago,
            pago_actual=Decimal("30.00"),
        )

    resultados = ejecutar_en_paralelo(
        [("cobro-uno", lambda: cobrar("Uno")), ("cobro-dos", lambda: cobrar("Dos"))]
    )

    assert sum(resultado[1] == "ok" for resultado in resultados) == 1
    assert Recibo.objects.filter(pedido=pedido, estado="EMITIDO").count() == 1
    assert Recibo.objects.get(pedido=pedido).pago_actual == Decimal("30.00")


@pytest.mark.concurrency
@pytest.mark.django_db(transaction=True)
def test_emision_concurrente_de_nota_crea_solo_una(django_user_model):
    actor = django_user_model.objects.create_user(username="nota-concurrente")
    producto = silla(actor, sku="NOTA-CONCURRENTE")
    cargar_stock(producto, actor, 1)
    proforma, _ = proforma_enviada(actor, producto)
    pedido = aprobar_proforma(proforma_id=proforma.id, actor=actor)
    pedido.estado = valor("ESTADO_PEDIDO", "EN_PRODUCCION")
    pedido.save(update_fields=["estado"])
    pedido.estado = valor("ESTADO_PEDIDO", "LISTO_ENTREGA")
    pedido.save(update_fields=["estado"])

    resultados = ejecutar_en_paralelo(
        [
            ("nota-uno", lambda: emitir_nota(pedido=pedido, actor=actor)),
            ("nota-dos", lambda: emitir_nota(pedido=pedido, actor=actor)),
        ]
    )

    assert sum(resultado[1] == "ok" for resultado in resultados) == 1
    assert NotaEntrega.objects.filter(pedido=pedido).count() == 1
