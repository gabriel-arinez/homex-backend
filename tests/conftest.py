import pytest

from tests.factories import NOMBRES, valor


@pytest.fixture(autouse=True)
def catalogo_estructural(db):
    """Repone los valores estructurales tras el flush de pruebas transaccionales."""
    for concepto, valores in NOMBRES.items():
        for codigo in valores:
            valor(concepto, codigo)


@pytest.fixture(autouse=True)
def transiciones_pedido(db):
    from apps.pedidos.models import TransicionEstadoPedido
    from tests.factories import valor

    TransicionEstadoPedido.objects.get_or_create(
        estado_origen=valor("ESTADO_PEDIDO", "CONFIRMADO"),
        estado_destino=valor("ESTADO_PEDIDO", "CANCELADO"),
    )
