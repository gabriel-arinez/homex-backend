import pytest

from tests.factories import NOMBRES, valor


@pytest.fixture(autouse=True)
def catalogo_estructural(db):
    """Repone los valores estructurales tras el flush de pruebas transaccionales."""
    for concepto, valores in NOMBRES.items():
        for codigo in valores:
            valor(concepto, codigo)
