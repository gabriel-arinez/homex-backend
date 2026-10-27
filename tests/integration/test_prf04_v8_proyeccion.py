"""Proyección PRF04_2 de rectificaciones v8 con PostgreSQL de pruebas."""

import pytest

from apps.capturas.nlp import AdaptadorNLP
from apps.capturas.proyeccion_prf03 import proyectar

pytestmark = pytest.mark.django_db


def preparar(texto):
    resultado = AdaptadorNLP().extraer(
        solicitud_id="v8-proyeccion-regresion", texto=texto, moneda="BOB"
    )
    return proyectar(resultado.resultado_original)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Un escritorio con tres cajones, no, mejor dos cajones", "cajones"),
        ("Un escritorio con tres cajones, no, mejor dos", "cajones"),
        ("Un escritorio con tres cajones, no, mejor dos puertas", "puertas"),
    ],
)
def test_nueva_cantidad_llega_a_configurador_sin_duplicados(texto, esperado):
    proyeccion = preparar(texto)
    assert proyeccion["version_proyeccion"] == "PRF04_2"
    componentes = proyeccion["especificacion"]["datos_tecnicos"]["componentes"]
    assert len(componentes) == 1
    assert componentes[0]["nombre"].lower() == esperado
    assert componentes[0]["cantidad_interna"] == 2
    assert any(p["codigo"] == "CONFLICTING_VALUES" for p in proyeccion["pendientes"])


def test_ambiguedad_no_inventa_pieza_ni_cantidad():
    proyeccion = preparar("Un escritorio con tres cajones, no, dos cajones")
    componentes = proyeccion["especificacion"]["datos_tecnicos"]["componentes"]
    assert componentes == []
    assert any(p["codigo"] == "CONFLICTING_VALUES" for p in proyeccion["pendientes"])


def test_monto_total_inalterado_con_correcion_interna():
    proyeccion = preparar("Una mesa con tres cajones, no, mejor dos, total 7300 bolivianos")
    assert proyeccion["comercial"]["precio_unitario"] is None
    assert any(
        p["codigo"] == "TOTAL_NEGOCIADO" and p["total_negociado"] == "7300.00"
        for p in proyeccion["pendientes"]
    )
