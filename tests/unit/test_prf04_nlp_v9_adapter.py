"""Contrato de adaptador v9: rectificaciones ASR sin puntuación y sin confirmación tácita."""

import pytest

from apps.capturas.nlp import AdaptadorNLP


@pytest.fixture(autouse=True)
def catalogo_estructural():
    yield


@pytest.fixture(autouse=True)
def transiciones_pedido():
    yield


def extraer(texto):
    return AdaptadorNLP().extraer(solicitud_id="backend-v9-puntuacion", texto=texto, moneda="BOB")


def cantidades(resultado, decision):
    return [
        (c["text"].casefold(), c["normalized_value"])
        for c in resultado.candidatos
        if c["label"] == "CANTIDAD_INTERNA" and c["decision"] == decision
    ]


@pytest.mark.parametrize(
    "texto",
    [
        "Un escritorio con tres cajones no mejor dos cajones",
        "Un escritorio con tres cajones no, mejor dos cajones",
        "Un escritorio con tres cajones. No, mejor dos cajones",
        "Un escritorio con tres cajones no mejor dos",
    ],
)
def test_rectificacion_asr_sin_puntuacion(texto):
    resultado = extraer(texto)
    assert resultado.estado == "REQUIRES_REVIEW"
    assert resultado.motor["rules_version"] == "prf04-rules-v14"
    assert [c["name"].lower() for c in resultado.propuesta.componentes] == ["cajones"]
    assert cantidades(resultado, "ACCEPTED") == [("dos", 2)]
    assert cantidades(resultado, "REJECTED") == [("tres", 3)]
    assert any(w["code"] == "CONFLICTING_VALUES" for w in resultado.advertencias)
    assert all(
        resultado.texto_original[c["start"] : c["end"]] == c["text"] for c in resultado.candidatos
    )


@pytest.mark.parametrize(
    "texto",
    [
        "Un escritorio con tres cajones no, dos",
        "Un escritorio con tres cajones no mejor dos no mejor cuatro",
    ],
)
def test_ambiguas_sin_cantidad_aceptada(texto):
    resultado = extraer(texto)
    assert cantidades(resultado, "ACCEPTED") == []
    assert resultado.propuesta.evidencia_pendiente
    assert any(w["code"] == "CONFLICTING_VALUES" for w in resultado.advertencias)


def test_no_fusionar_componentes_independientes():
    resultado = extraer("Un escritorio con tres cajones y dos puertas")
    assert [c["name"] for c in resultado.propuesta.componentes] == ["cajones", "puertas"]
    assert cantidades(resultado, "ACCEPTED") == [("tres", 3), ("dos", 2)]


def test_rectificacion_no_modifica_precio_total():
    resultado = extraer("Una mesa con tres cajones no mejor dos, total 7300 bolivianos")
    assert resultado.propuesta.precio["mode"] == "TOTAL_NEGOCIADO"
    assert resultado.propuesta.precio["line_total"] == "7300.00"
    assert resultado.propuesta.precio["unit_price_input"] is None


def test_sin_ner_ni_escritura_comercial():
    resultado = extraer("Escritorio con tres cajones no mejor dos")
    assert resultado.motor["mode"] == "RULES_ONLY"
    assert resultado.propuesta.cantidad is None
    assert resultado.estado == "REQUIRES_REVIEW"
