"""The live worker gate must check the operational and historical distributions."""

import importlib.util
from hashlib import sha256
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def catalogo_estructural():
    yield


@pytest.fixture(autouse=True)
def transiciones_pedido():
    yield


@pytest.fixture
def gate(monkeypatch):
    path = Path(__file__).parents[2] / "scripts/verificar_integracion_f084.py"
    spec = importlib.util.spec_from_file_location("worker_identity_gate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []

    class FakeRedis:
        @staticmethod
        def from_url(url):
            calls.append(url)
            return FakeRedis()

        def ping(self):
            return True

    monkeypatch.setattr(module, "Redis", FakeRedis)
    return module, calls


def test_operational_wheel_matches_installed_release_and_keeps_historical_gate(gate):
    module, calls = gate
    assert module.version("homex-nlp") == "0.1.22"
    assert module.WHEEL.name == "homex_nlp-0.1.22-py3-none-any.whl"
    assert sha256(module.WHEEL.read_bytes()).hexdigest() == module.WHEEL_SHA256
    assert module.WHEEL_F08.name == "homex_nlp-0.1.1-py3-none-any.whl"
    assert module.WHEEL_F08_SHA256 == (
        "28c5e28c984783e4efe3139dfd295878798a4b0ade033719c8d460b58917768f"
    )
    module.verificar_runtime()
    assert len(calls) == 1


def test_unknown_installed_version_stops_before_redis(gate, monkeypatch):
    module, calls = gate
    monkeypatch.setattr(module, "version", lambda _: "9.0.0")
    with pytest.raises(AssertionError, match="worker no utiliza"):
        module.verificar_runtime()
    assert calls == []


@pytest.mark.parametrize("attribute", ["WHEEL", "WHEEL_F08"])
def test_corrupted_operational_or_historical_wheel_stops_before_redis(
    gate, monkeypatch, tmp_path, attribute
):
    module, calls = gate
    corrupted = tmp_path / "corrupted.whl"
    corrupted.write_bytes(b"not the pinned wheel")
    monkeypatch.setattr(module, attribute, corrupted)
    with pytest.raises(AssertionError, match="hash"):
        module.verificar_runtime()
    assert calls == []
