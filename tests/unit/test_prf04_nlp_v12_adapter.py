"""Regresiones aisladas de Backend PRF04 y NLP v12: números dimensionales en palabras."""

import pytest

from apps.capturas.nlp import AdaptadorNLP


@pytest.fixture(autouse=True)
def catalogo_estructural():
    yield


@pytest.fixture(autouse=True)
def transiciones_pedido():
    yield


def extraer(texto):
    return AdaptadorNLP().extraer(solicitud_id="backend-v12-numeros", texto=texto, moneda="BOB")


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        (
            "Un ropero de dos metros de alto y 90 centímetros de ancho",
            {"alto": "2000", "ancho": "900"},
        ),
        (
            "Un ropero de 2 metros de alto y noventa centímetros de ancho",
            {"alto": "2000", "ancho": "900"},
        ),
        (
            "Un ropero de dos metros de alto y noventa centímetros de ancho",
            {"alto": "2000", "ancho": "900"},
        ),
        ("Una mesa con altura setenta y cinco centímetros", {"alto": "750"}),
        ("Un escritorio de ancho ciento ochenta centímetros", {"ancho": "1800"}),
        ("Un ropero de mil ochocientos milímetros de alto", {"alto": "1800"}),
    ],
)
def test_medidas_en_palabras_sin_precio_inventado(texto, esperado):
    r = extraer(texto)
    assert r.estado == "REQUIRES_REVIEW"
    assert r.motor["rules_version"] == "prf04-rules-v14"
    assert r.motor["mode"] == "RULES_ONLY"
    assert r.propuesta is not None
    assert r.propuesta.precio is None
    medidas = {
        m["axis"]: m["value_mm"] for m in r.propuesta.dimensiones if m["component_ref"] is None
    }
    assert medidas == esperado
    assert all(r.texto_original[c["start"] : c["end"]] == c["text"] for c in r.candidatos)


def test_precio_real_se_conserva_con_medida_en_palabras():
    r = extraer("Una mesa con altura noventa centímetros, total 7600 bolivianos")
    assert r.propuesta is not None
    assert r.propuesta.precio["mode"] == "TOTAL_NEGOCIADO"
    assert r.propuesta.precio["line_total"] == "7600.00"
    assert [d["value_mm"] for d in r.propuesta.dimensiones] == ["900"]


@pytest.mark.parametrize(
    "texto",
    [
        "Un ropero de alto dos",
        "Un ropero de alto dos coma cinco metros",
        "Un ropero de alto ciento y veinte centímetros",
        "Una mesa de dos metros",
    ],
)
def test_abstencion_de_medidas_incompletas(texto):
    r = extraer(texto)
    assert r.propuesta is not None
    assert r.propuesta.dimensiones == ()
    assert r.propuesta.precio is None
