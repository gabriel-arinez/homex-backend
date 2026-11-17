"""Synthetic commercial dictations must exercise, not bypass, assistant limits."""

import importlib
from pathlib import Path

import pytest

from apps.capturas.limites import contar_palabras_comerciales


@pytest.fixture(autouse=True)
def catalogo_estructural():
    """No database is needed to inspect fixture source strings."""


@pytest.fixture(autouse=True)
def transiciones_pedido():
    """Override the database-seeding fixture for this pure script check."""


def test_all_commercial_audio_texts_meet_current_operational_limits(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    furniture = importlib.import_module("generar_audio_sintetico_prf04")
    catalog = importlib.import_module("generar_audio_catalogo")
    for text in [furniture.TEXTO, *catalog.SAMPLES.values()]:
        assert contar_palabras_comerciales(text) >= 20
        assert len(text) <= 3000
