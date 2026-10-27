"""Regresiones v8 de rectificaciones internas: contrato backend sin PostgreSQL."""

import pytest

from apps.capturas.nlp import AdaptadorNLP


@pytest.fixture(autouse=True)
def catalogo_estructural():
    yield


@pytest.fixture(autouse=True)
def transiciones_pedido():
    yield


def extraer(texto):
    return AdaptadorNLP().extraer(solicitud_id="prf04-v8-regresiones", texto=texto, moneda="BOB")


def cantidades(resultado, decision):
    return [
        (c["text"].lower(), c["normalized_value"])
        for c in resultado.candidatos
        if c["label"] == "CANTIDAD_INTERNA" and c["decision"] == decision
    ]


@pytest.mark.parametrize(
    ("texto", "piezas"),
    [
        ("Un escritorio con tres cajones, no, mejor dos cajones", ["cajones"]),
        ("Un escritorio con tres cajones, no, mejor dos", ["cajones"]),
        ("Un escritorio con tres cajones, no, mejor dos puertas", ["puertas"]),
    ],
)
def test_corrige_pieza_y_cantidad_sin_afirmar_la_antigua(texto, piezas):
    r = extraer(texto)
    assert r.estado == "REQUIRES_REVIEW"
    assert r.motor["rules_version"] == "prf04-rules-v15"
    assert [c["name"].lower() for c in r.propuesta.componentes] == piezas
    assert cantidades(r, "ACCEPTED") == [("dos", 2)]
    assert cantidades(r, "REJECTED") == [("tres", 3)]
    assert any(w["code"] == "CONFLICTING_VALUES" for w in r.advertencias)
    assert all(r.texto_original[c["start"] : c["end"]] == c["text"] for c in r.candidatos)


def test_piezas_independientes_no_se_pierden():
    r = extraer("Un escritorio con tres cajones y dos puertas")
    assert [c["name"] for c in r.propuesta.componentes] == ["cajones", "puertas"]
    assert cantidades(r, "ACCEPTED") == [("tres", 3), ("dos", 2)]


def test_rectificacion_ambigua_no_se_proyecta_como_confirmada():
    r = extraer("Un escritorio con tres cajones, no, dos")
    assert r.estado == "REQUIRES_REVIEW"
    assert cantidades(r, "ACCEPTED") == []
    assert any(c["decision"] == "UNRESOLVED" for c in r.candidatos)
    assert any(w["code"] == "CONFLICTING_VALUES" for w in r.advertencias)


def test_precio_negociado_literal_no_se_inventa_unitario():
    r = extraer("Una mesa con tres cajones, no, mejor dos, total 7300 bolivianos")
    assert r.propuesta.precio["mode"] == "TOTAL_NEGOCIADO"
    assert r.propuesta.precio["line_total"] == "7300.00"
    assert r.propuesta.cantidad == 1


def test_cantidad_interna_no_es_cantidad_de_muebles():
    r = extraer("Escritorio con tres cajones, no, mejor dos")
    assert r.propuesta.cantidad is None
    assert cantidades(r, "ACCEPTED") == [("dos", 2)]
