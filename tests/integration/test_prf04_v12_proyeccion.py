"""Proyección v12 de números dimensionales en palabras (PostgreSQL descartable en CI)."""

import pytest

from apps.capturas.nlp import AdaptadorNLP
from apps.capturas.proyeccion_prf03 import proyectar

pytestmark = pytest.mark.django_db


def preparar(texto):
    r = AdaptadorNLP().extraer(solicitud_id="backend-v12-proyeccion", texto=texto, moneda="BOB")
    return proyectar(r.resultado_original)


def test_l06_ambas_dimensiones_equivalentes_en_proyeccion():
    p = preparar("Un ropero de dos metros de alto y noventa centímetros de ancho")
    assert p["version_proyeccion"] == "PRF04_2"
    generales = p["especificacion"]["datos_tecnicos"]["caracteristicas_generales"]
    assert generales["dimensiones"] == {
        "alto": {"valor": "2", "unidad": "m"},
        "ancho": {"valor": "90", "unidad": "cm"},
    }
    assert p["comercial"]["precio_unitario"] is None
    assert not any(x["codigo"] == "TOTAL_NEGOCIADO" for x in p["pendientes"])


def test_precio_explicitamente_dictado_no_se_inventa_ni_se_pierde():
    p = preparar("Una mesa de altura setenta y cinco centímetros, total 7600 bolivianos")
    assert p["comercial"]["precio_unitario"] is None
    dimensiones = p["especificacion"]["datos_tecnicos"]["caracteristicas_generales"]["dimensiones"]
    assert dimensiones["alto"] == {"valor": "75", "unidad": "cm"}
    assert any(
        x["codigo"] == "TOTAL_NEGOCIADO" and x["total_negociado"] == "7600.00"
        for x in p["pendientes"]
    )


def test_milimetros_con_tilde_conserva_unidad_real():
    p = preparar("Un ropero de mil ochocientos milímetros de alto")
    dimensiones = p["especificacion"]["datos_tecnicos"]["caracteristicas_generales"]["dimensiones"]
    assert dimensiones["alto"] == {"valor": "1800", "unidad": "mm"}
