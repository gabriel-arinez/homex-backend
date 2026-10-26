"""Contrato Backend PRF-04 v11: componentes y medidas sin errores inventados."""

import pytest

from apps.capturas.nlp import AdaptadorNLP


@pytest.fixture(autouse=True)
def catalogo_estructural():
    yield


@pytest.fixture(autouse=True)
def transiciones_pedido():
    yield


def extraer(texto):
    return AdaptadorNLP().extraer(solicitud_id="backend-v11-limpios", texto=texto, moneda="BOB")


def test_credenza_estantes_son_componentes():
    r = extraer("Una credenza con cuatro puertas y dos estantes")
    assert r.estado == "REQUIRES_REVIEW"
    assert r.motor["rules_version"] == "prf04-rules-v13"
    assert r.propuesta.nombre.lower() == "credenza"
    assert [c["name"].lower() for c in r.propuesta.componentes] == ["puertas", "estantes"]
    internas = [
        c["normalized_value"]
        for c in r.candidatos
        if c["label"] == "CANTIDAD_INTERNA" and c["decision"] == "ACCEPTED"
    ]
    assert internas == [4, 2]


def test_cajonera_no_se_duplica_como_componente():
    r = extraer("Una cajonera con seis cajones")
    assert r.propuesta.nombre.lower() == "cajonera"
    assert [c["name"].lower() for c in r.propuesta.componentes] == ["cajones"]
    assert any(
        c["label"] == "CANTIDAD_INTERNA" and c["normalized_value"] == 6 for c in r.candidatos
    )


@pytest.mark.parametrize(
    ("texto", "eje", "milimetros"),
    [
        ("Un escritorio de ancho total 180 centímetros", "ancho", "1800"),
        ("Una mesa con altura total 75 centímetros", "alto", "750"),
    ],
)
def test_dimensiones_total_sin_precio(texto, eje, milimetros):
    r = extraer(texto)
    assert r.propuesta.precio is None
    medidas = {
        d["axis"]: d["value_mm"] for d in r.propuesta.dimensiones if d["component_ref"] is None
    }
    assert medidas[eje] == milimetros
    assert r.motor["mode"] == "RULES_ONLY"
    assert all(r.texto_original[c["start"] : c["end"]] == c["text"] for c in r.candidatos)


@pytest.mark.parametrize(
    "texto",
    ["Dos mesas y tres estantes", "Una credenza con dos estantes y otro escritorio"],
)
def test_pedidos_realmente_distintos_se_abstienen(texto):
    r = extraer(texto)
    assert r.estado == "NO_PROPOSAL"
    assert r.propuesta is None
    assert any(w["code"] == "MULTIPLE_MAIN_PRODUCTS" for w in r.advertencias)


def test_precio_real_posterior_no_se_pierde():
    r = extraer("Una mesa con altura total 75 cm, precio total 2000 bolivianos")
    assert r.propuesta.precio["mode"] == "TOTAL_NEGOCIADO"
    assert r.propuesta.precio["line_total"] == "2000.00"
