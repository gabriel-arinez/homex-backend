"""Regresiones NLP v10 de precios inequívocos, sin PostgreSQL."""

import pytest

from apps.capturas.nlp import AdaptadorNLP


@pytest.fixture(autouse=True)
def catalogo_estructural():
    yield


@pytest.fixture(autouse=True)
def transiciones_pedido():
    yield


def extraer(texto):
    return AdaptadorNLP().extraer(solicitud_id="backend-v10-precios", texto=texto, moneda="BOB")


@pytest.mark.parametrize(
    "texto",
    [
        "Un escritorio de ancho total 180 centímetros",
        "Un escritorio de altura total 180 centímetros",
        "Un escritorio con ancho total 180 cm y alto 75 cm",
        "Escritorio precio total 180 centímetros",
        "Escritorio monto total de 200 mm",
    ],
)
def test_medidas_no_generan_precio_comercial(texto):
    resultado = extraer(texto)
    assert resultado.estado == "REQUIRES_REVIEW"
    assert resultado.motor["rules_version"] == "prf04-rules-v16"
    assert resultado.propuesta.precio is None
    assert all(
        resultado.texto_original[c["start"] : c["end"]] == c["text"] for c in resultado.candidatos
    )


@pytest.mark.parametrize(
    ("texto", "monto", "modo"),
    [
        ("Escritorio ancho total 180 cm, total 7600 bolivianos", "7600.00", "TOTAL_NEGOCIADO"),
        ("Escritorio con alto total 75 cm. Precio total de 2000 Bs", "2000.00", "TOTAL_NEGOCIADO"),
        ("Escritorio a 500 Bs por unidad", "500.00", "PRECIO_UNITARIO"),
    ],
)
def test_precio_explicito_posterior_preservado(texto, monto, modo):
    resultado = extraer(texto)
    assert resultado.propuesta.precio is not None
    assert resultado.propuesta.precio["mode"] == modo
    assert resultado.propuesta.precio["stated_amount"] == monto


def test_dos_componentes_limpios_se_preservan():
    resultado = extraer("Un escritorio con dos cajones y tres puertas")
    assert [c["name"].lower() for c in resultado.propuesta.componentes] == ["cajones", "puertas"]
    assert resultado.propuesta.precio is None
