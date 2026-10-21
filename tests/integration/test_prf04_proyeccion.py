import pytest
from homex_nlp.contracts import ExtractionRequest
from homex_nlp.engine import RulesEngine

from apps.capturas.proyeccion_prf03 import proyectar
from apps.proformas.validacion_tecnica import validar_datos_tecnicos

pytestmark = pytest.mark.django_db


def proyecto(texto):
    raw = RulesEngine().extract(
        ExtractionRequest(request_id="proyeccion-prf04", text=texto, currency_context="BOB")
    )
    return proyectar(raw.model_dump(mode="json"))


def test_cantidades_espesores_y_asociaciones_en_ficha():
    p = proyecto("Seis veladores con dos cajones, tapa de melamina MDP 25 mm; panel frontal 18 mm")
    assert p["comercial"]["cantidad"] == 6
    piezas = p["especificacion"]["datos_tecnicos"]["componentes"]
    assert piezas[0]["cantidad_interna"] == 2
    assert piezas[1]["espesor"] == "25 mm"
    assert piezas[1]["material"] == "melamina MDP"
    assert piezas[2]["espesor"] == "18 mm"
    assert "material" not in piezas[2]
    validar_datos_tecnicos(p["especificacion"]["datos_tecnicos"])


def test_conjunto_explicito_genera_uids_estables_y_vinculos():
    p = proyecto("Un escritorio, conjunto inferior: tapa de 25 mm; panel frontal 18 mm")
    datos = p["especificacion"]["datos_tecnicos"]
    assert len(datos["conjuntos"]) == 1
    assert all(c["conjunto_uid"] == datos["conjuntos"][0]["uid"] for c in datos["componentes"])
    assert p == proyecto("Un escritorio, conjunto inferior: tapa de 25 mm; panel frontal 18 mm")


def test_ejes_ambiguos_y_precio_total_no_se_inventan():
    p = proyecto("Tres escritorios en L de 140x140, total 100 bolivianos")
    assert p["comercial"]["precio_unitario"] is None
    assert "dimensiones" not in p["especificacion"]["datos_tecnicos"]["caracteristicas_generales"]
    assert {a["codigo"] for a in p["pendientes"]} >= {"MISSING_AXIS", "TOTAL_NEGOCIADO"}


def test_medida_inequivoca_no_requiere_confirmacion():
    p = proyecto("Un escritorio de 43 cm de ancho")
    dims = p["especificacion"]["datos_tecnicos"]["caracteristicas_generales"]["dimensiones"]
    assert dims["ancho"] == {"valor": "43", "unidad": "cm"}
    assert not any(a["codigo"] in {"MISSING_AXIS", "MISSING_UNIT"} for a in p["pendientes"])


def test_dimension_de_pieza_no_se_reubica_como_general():
    p = proyecto("Una mesa de largo 250 cm; tapa de 43 cm de ancho")
    datos = p["especificacion"]["datos_tecnicos"]
    assert datos["caracteristicas_generales"]["dimensiones"] == {
        "largo": {"valor": "250", "unidad": "cm"}
    }
    assert datos["componentes"][0]["dimensiones"] == "ancho: 43 cm"
