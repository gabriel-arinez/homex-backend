from decimal import Decimal

import pytest

from apps.notas_entrega.models import NotaEntrega
from apps.notas_entrega.services import emitir_nota
from apps.recibos.models import Recibo
from apps.recibos.services import emitir_recibo
from tests.factories import valor
from tests.integration.test_f073_ventas import ejecutar_en_paralelo
from tests.integration.test_f074_cobros import crear_pedido_confirmado


def avanzar_a_listo_entrega(pedido):
    pedido.estado = valor(
        "ESTADO_PEDIDO",
        "EN_PRODUCCION",
    )
    pedido.save(
        update_fields=["estado"],
    )

    pedido.estado = valor(
        "ESTADO_PEDIDO",
        "LISTO_ENTREGA",
    )
    pedido.save(
        update_fields=["estado"],
    )

    pedido.refresh_from_db()

    return pedido


def cobrar(
    *,
    pedido,
    actor,
    nombre,
    pago,
):
    return emitir_recibo(
        pedido=pedido,
        actor=actor,
        nombre_completo=nombre,
        monto_en_letras="monto concurrente",
        concepto="Anticipo",
        tipo_pago=valor(
            "TIPO_PAGO",
            "EFECTIVO",
        ),
        pago_actual=Decimal(pago),
    )


@pytest.mark.concurrency
@pytest.mark.django_db(transaction=True)
def test_cobros_concurrentes_no_superan_el_saldo(
    django_user_model,
):
    actor = django_user_model.objects.create_user(
        username="cobros-concurrentes",
    )

    pedido, _ = crear_pedido_confirmado(
        actor,
        sku="COBROS-CONCURRENTES",
    )

    resultados = ejecutar_en_paralelo(
        [
            (
                "cobro-uno",
                lambda: cobrar(
                    pedido=pedido,
                    actor=actor,
                    nombre="Uno",
                    pago="30.00",
                ),
            ),
            (
                "cobro-dos",
                lambda: cobrar(
                    pedido=pedido,
                    actor=actor,
                    nombre="Dos",
                    pago="30.00",
                ),
            ),
        ]
    )

    assert sum(resultado[1] == "ok" for resultado in resultados) == 1

    recibos = Recibo.objects.filter(
        pedido=pedido,
        estado="EMITIDO",
    )

    assert recibos.count() == 1
    assert recibos.get().pago_actual == Decimal("30.00")
    assert recibos.get().saldo == Decimal("20.00")


@pytest.mark.concurrency
@pytest.mark.django_db(transaction=True)
def test_emision_concurrente_de_nota_crea_solo_una(
    django_user_model,
):
    actor = django_user_model.objects.create_user(
        username="nota-concurrente",
    )

    pedido, _ = crear_pedido_confirmado(
        actor,
        sku="NOTA-CONCURRENTE",
    )

    avanzar_a_listo_entrega(
        pedido,
    )

    resultados = ejecutar_en_paralelo(
        [
            (
                "nota-uno",
                lambda: emitir_nota(
                    pedido=pedido,
                    actor=actor,
                ),
            ),
            (
                "nota-dos",
                lambda: emitir_nota(
                    pedido=pedido,
                    actor=actor,
                ),
            ),
        ]
    )

    assert sum(resultado[1] == "ok" for resultado in resultados) == 1

    assert (
        NotaEntrega.objects.filter(
            pedido=pedido,
        ).count()
        == 1
    )


@pytest.mark.concurrency
@pytest.mark.django_db(transaction=True)
def test_secuencia_recibos_no_duplica_numeros_bajo_concurrencia(
    django_user_model,
):
    actor = django_user_model.objects.create_user(
        username="secuencia-recibos",
    )

    pedido_uno, _ = crear_pedido_confirmado(
        actor,
        sku="SEQ-RECIBO-UNO",
    )

    pedido_dos, _ = crear_pedido_confirmado(
        actor,
        sku="SEQ-RECIBO-DOS",
    )

    resultados = ejecutar_en_paralelo(
        [
            (
                "recibo-uno",
                lambda: cobrar(
                    pedido=pedido_uno,
                    actor=actor,
                    nombre="Uno",
                    pago="10.00",
                ),
            ),
            (
                "recibo-dos",
                lambda: cobrar(
                    pedido=pedido_dos,
                    actor=actor,
                    nombre="Dos",
                    pago="10.00",
                ),
            ),
        ]
    )

    assert sum(resultado[1] == "ok" for resultado in resultados) == 2

    numeros = list(
        Recibo.objects.filter(
            pedido__in=[
                pedido_uno,
                pedido_dos,
            ]
        ).values_list(
            "numero",
            flat=True,
        )
    )

    assert len(numeros) == 2
    assert len(set(numeros)) == 2


@pytest.mark.concurrency
@pytest.mark.django_db(transaction=True)
def test_secuencia_notas_no_duplica_numeros_bajo_concurrencia(
    django_user_model,
):
    actor = django_user_model.objects.create_user(
        username="secuencia-notas",
    )

    pedido_uno, _ = crear_pedido_confirmado(
        actor,
        sku="SEQ-NOTA-UNO",
    )

    pedido_dos, _ = crear_pedido_confirmado(
        actor,
        sku="SEQ-NOTA-DOS",
    )

    avanzar_a_listo_entrega(
        pedido_uno,
    )

    avanzar_a_listo_entrega(
        pedido_dos,
    )

    resultados = ejecutar_en_paralelo(
        [
            (
                "nota-uno",
                lambda: emitir_nota(
                    pedido=pedido_uno,
                    actor=actor,
                ),
            ),
            (
                "nota-dos",
                lambda: emitir_nota(
                    pedido=pedido_dos,
                    actor=actor,
                ),
            ),
        ]
    )

    assert sum(resultado[1] == "ok" for resultado in resultados) == 2

    numeros = list(
        NotaEntrega.objects.filter(
            pedido__in=[
                pedido_uno,
                pedido_dos,
            ]
        ).values_list(
            "numero",
            flat=True,
        )
    )

    assert len(numeros) == 2
    assert len(set(numeros)) == 2
