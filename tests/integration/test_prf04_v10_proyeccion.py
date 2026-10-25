"""Proyección de precios NLP v10: requiere PostgreSQL descartable."""

import pytest

from apps.capturas.nlp import AdaptadorNLP
from apps.capturas.proyeccion_prf03 import proyectar

pytestmark = pytest.mark.django_db


def preparar(texto):
    resultado = AdaptadorNLP().extraer(
        solicitud_id="backend-v10-proyeccion", texto=texto, moneda="BOB"
    )
    return proyectar(resultado.resultado_original)


@pytest.mark.parametrize(
    "texto",
    [
        "Un escritorio de ancho total 180 centímetros",
        "Un escritorio con ancho total 180 cm y alto 75 cm",
    ],
)
def test_no_inventar_precio_desde_medida(texto):
    propuesta = preparar(texto)
    assert propuesta["version_proyeccion"] == "PRF04_2"
    assert propuesta["comercial"]["precio_unitario"] is None
    assert not any(p["codigo"] == "TOTAL_NEGOCIADO" for p in propuesta["pendientes"])


def test_total_legitimo_posterior_se_mantiene_pendiente():
    propuesta = preparar("Un escritorio con ancho total 180 cm, total 7600 bolivianos")
    assert propuesta["comercial"]["precio_unitario"] is None
    assert any(
        p["codigo"] == "TOTAL_NEGOCIADO" and p["total_negociado"] == "7600.00"
        for p in propuesta["pendientes"]
    )
