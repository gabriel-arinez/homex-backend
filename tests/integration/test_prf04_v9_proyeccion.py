"""Proyección PRF-04 v9 hacia ficha PRF-03 con PostgreSQL aislado de CI."""

import pytest

from apps.capturas.nlp import AdaptadorNLP
from apps.capturas.proyeccion_prf03 import proyectar

pytestmark = pytest.mark.django_db


def preparar(texto):
    resultado = AdaptadorNLP().extraer(
        solicitud_id="v9-proyeccion-regresion", texto=texto, moneda="BOB"
    )
    return proyectar(resultado.resultado_original)


@pytest.mark.parametrize(
    "texto",
    [
        "Un escritorio con tres cajones no mejor dos cajones",
        "Un escritorio con tres cajones no, mejor dos cajones",
        "Un escritorio con tres cajones no mejor dos",
        "Un escritorio con tres cajones. No mejor dos",
    ],
)
def test_solo_cantidad_rectificada_se_proyecta(texto):
    propuesta = preparar(texto)
    piezas = propuesta["especificacion"]["datos_tecnicos"]["componentes"]
    assert len(piezas) == 1
    assert piezas[0]["nombre"].lower() == "cajones"
    assert piezas[0]["cantidad_interna"] == 2
    assert propuesta["version_proyeccion"] == "PRF04_2"
    assert any(p["codigo"] == "CONFLICTING_VALUES" for p in propuesta["pendientes"])


def test_encadenamiento_sin_cantidad_confirmada():
    propuesta = preparar("Un escritorio con tres cajones no mejor dos no mejor cuatro")
    piezas = propuesta["especificacion"]["datos_tecnicos"]["componentes"]
    assert len(piezas) == 1
    assert "cantidad_interna" not in piezas[0]
    assert any(p["codigo"] == "CONFLICTING_VALUES" for p in propuesta["pendientes"])


def test_precio_total_no_se_convierte_a_unitario():
    propuesta = preparar("Una mesa con tres cajones no mejor dos, total 7300 bolivianos")
    assert propuesta["comercial"]["precio_unitario"] is None
    assert any(
        p["codigo"] == "TOTAL_NEGOCIADO" and p["total_negociado"] == "7300.00"
        for p in propuesta["pendientes"]
    )
