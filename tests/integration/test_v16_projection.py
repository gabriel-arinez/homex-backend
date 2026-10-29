"""V16 integration with the real adapter, catalogue and PRF-03 validator."""

import pytest

from apps.capturas.nlp import AdaptadorNLP
from apps.capturas.proyeccion_prf03 import proyectar
from apps.proformas.validacion_tecnica import validar_datos_tecnicos

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "text",
    [
        "Dos escritorios operativos con tapa de 25 mm y laterales de 18 mm, precio unitario 1500",
        "Un escritorio con dos puertas abatibles y tres repisas interiores",
        "Dos gaveteros móviles con cuatro cajones",
        "Un estante de pared con tres repisas abiertas",
        "Un escritorio blanco o nogal",
        "Un escritorio ancho 120 y alto 75 cm",
        "Dos escritorios precio total 100, sin descuento",
        "Un escritorio precio unitario 1500, corrijo, 1700",
        "Un escritorio sin puertas blancas",
    ],
)
def test_real_projection_accepts_v16_and_keeps_original(text):
    r = AdaptadorNLP().extraer(solicitud_id="v16-integration", texto=text, moneda="BOB")
    p = proyectar(r.resultado_original)
    assert p is not None
    validar_datos_tecnicos(p["especificacion"]["datos_tecnicos"])
    assert p == proyectar(r.resultado_original)
    assert p["especificacion"]["datos_tecnicos"]["descripcion_original"] == text


def test_exact_total_reference_is_not_an_effective_unit_price():
    raw = (
        AdaptadorNLP()
        .extraer(
            solicitud_id="v16-total", texto="Dos mesas precio total 100 sin descuento", moneda="BOB"
        )
        .resultado_original
    )
    p = proyectar(raw)
    assert p["comercial"]["precio_unitario"] is None
    assert p["comercial"]["descuento"] == "0.00"
    assert any(w["codigo"] == "TOTAL_NEGOCIADO" for w in p["pendientes"])
