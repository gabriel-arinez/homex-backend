import pytest

from tests.factories import NOMBRES, valor

TRANSICIONES_PEDIDO = [
    ("CONFIRMADO", "EN_PRODUCCION"),
    ("EN_PRODUCCION", "LISTO_ENTREGA"),
    ("LISTO_ENTREGA", "ENTREGADO"),
    ("CONFIRMADO", "CANCELADO"),
    ("EN_PRODUCCION", "CANCELADO"),
    ("LISTO_ENTREGA", "CANCELADO"),
]


@pytest.fixture(autouse=True)
def catalogo_estructural(db):
    """Repone valores estructurales tras el flush de pruebas transaccionales."""
    for concepto, valores in NOMBRES.items():
        for codigo in valores:
            valor(
                concepto,
                codigo,
            )


@pytest.fixture(autouse=True)
def transiciones_pedido(db):
    from apps.pedidos.models import TransicionEstadoPedido

    for origen, destino in TRANSICIONES_PEDIDO:
        TransicionEstadoPedido.objects.get_or_create(
            estado_origen=valor(
                "ESTADO_PEDIDO",
                origen,
            ),
            estado_destino=valor(
                "ESTADO_PEDIDO",
                destino,
            ),
        )
