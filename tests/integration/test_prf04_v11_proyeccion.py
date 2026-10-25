"""Proyección PRF-04 v11 a ficha PRF-03 (PostgreSQL descartable CI)."""

import pytest

from apps.capturas.nlp import AdaptadorNLP
from apps.capturas.proyeccion_prf03 import proyectar

pytestmark = pytest.mark.django_db


def preparar(texto):
    r = AdaptadorNLP().extraer(solicitud_id="backend-v11-proyeccion", texto=texto, moneda="BOB")
    return proyectar(r.resultado_original)


def test_credenza_con_puertas_y_estantes():
    propuesta = preparar("Una credenza con cuatro puertas y dos estantes")
    assert propuesta["version_proyeccion"] == "PRF04_2"
    piezas = propuesta["especificacion"]["datos_tecnicos"]["componentes"]
    assert [(p["nombre"].lower(), p["cantidad_interna"]) for p in piezas] == [
        ("puertas", 4),
        ("estantes", 2),
    ]


def test_cajonera_no_se_duplica():
    propuesta = preparar("Una cajonera con seis cajones")
    piezas = propuesta["especificacion"]["datos_tecnicos"]["componentes"]
    assert len(piezas) == 1
    assert piezas[0]["nombre"].lower() == "cajones"
    assert piezas[0]["cantidad_interna"] == 6


@pytest.mark.parametrize(
    ("texto", "eje", "valor", "unidad"),
    [
        ("Un escritorio de ancho total 180 centímetros", "ancho", "180", "cm"),
        ("Una mesa con altura total 75 centímetros", "alto", "75", "cm"),
    ],
)
def test_medidas_reales_sin_precio_inventado(texto, eje, valor, unidad):
    propuesta = preparar(texto)
    dims = propuesta["especificacion"]["datos_tecnicos"]["caracteristicas_generales"]["dimensiones"]
    assert dims[eje] == {"valor": valor, "unidad": unidad}
    assert propuesta["comercial"]["precio_unitario"] is None
    assert not any(p["codigo"] == "TOTAL_NEGOCIADO" for p in propuesta["pendientes"])
