"""Real consumer of the frozen rules contract; no mocked NLP predictions."""

import pytest

from apps.capturas.nlp import AdaptadorNLP
from apps.capturas.proyeccion_prf03 import proyectar
from apps.proformas.validacion_tecnica import validar_datos_tecnicos

pytestmark = pytest.mark.django_db


def proposal(text):
    raw = AdaptadorNLP().extraer(solicitud_id="final", texto=text, moneda="BOB").resultado_original
    p = proyectar(raw)
    validar_datos_tecnicos(p["especificacion"]["datos_tecnicos"])
    return p


def test_unit_and_total_survive_without_inventing_quantity():
    p = proposal("Escritorio precio unitario 600 total 2400")
    assert p["comercial"]["cantidad"] is None
    assert p["comercial"]["precio_unitario"] == "600.00"
    assert p["comercial"]["descuento"] is None
    assert any(
        w["codigo"] == "TOTAL_NEGOCIADO" and w["total_negociado"] == "2400.00"
        for w in p["pendientes"]
    )


def test_pending_oral_thickness_has_structured_human_resolution():
    p = proposal("Un escritorio con tapacanto PVC de dos milímetros")
    warnings = [w for w in p["pendientes"] if w["codigo"] == "ESPESOR_SIN_COMPONENTE"]
    assert len(warnings) == 1
    assert warnings[0]["resolucion"]["valor"] == "2 mm"
    assert "espesor" not in str(
        p["especificacion"]["datos_tecnicos"].get("caracteristicas_generales", {})
    )
    assert not any(
        w["codigo"] == "REQUIRED_FIELD_MISSING" and "thicknesses" in w["ruta"]
        for w in p["pendientes"]
    )
