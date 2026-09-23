from hashlib import sha256
from pathlib import Path

import pytest

WHEEL = Path(__file__).parents[2] / "vendor" / "homex_nlp-0.1.0-py3-none-any.whl"
EXPECTED_SHA256 = "cfacc3a987f6158f43934cb64304fa50ea3e577cfa576f3db1e6d2a9576d19e6"


@pytest.fixture(autouse=True)
def catalogo_estructural():
    yield


@pytest.fixture(autouse=True)
def transiciones_pedido():
    yield


def test_wheel_fijado_con_hash_aprobado():
    assert WHEEL.is_file()
    assert sha256(WHEEL.read_bytes()).hexdigest() == EXPECTED_SHA256
