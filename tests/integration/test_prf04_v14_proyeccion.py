"""Regresiones de las capturas 23/24 y variantes orales, sin audio ni corpus nuevo."""

from copy import deepcopy

import pytest

from apps.capturas.nlp import AdaptadorNLP
from apps.capturas.proyeccion_prf03 import proyectar

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("material", ["melamine", "melamina"])
@pytest.mark.parametrize(
    "medida", ["un metro 20", "un metro veinte", "un metro y veinte centímetros"]
)
def test_capturas_23_24_dimensiones_evidencia_y_proyeccion(material, medida):
    texto = (
        f"Necesito un escritorio de {material} blanca, de {medida} de ancho, "
        "60 centímetros de profundidad y 75 centímetros de alto."
    )
    r = AdaptadorNLP().extraer(solicitud_id="capturas-23-24", texto=texto, moneda="BOB")
    original = deepcopy(r.resultado_original)
    assert r.version_contrato == "1.0"
    assert r.estado == "REQUIRES_REVIEW"
    assert r.motor["mode"] == "RULES_ONLY"
    assert r.motor["rules_version"] == "prf04-rules-v14"
    assert {d["axis"]: d["value_mm"] for d in r.propuesta.dimensiones} == {
        "ancho": "1200",
        "profundidad": "600",
        "alto": "750",
    }
    assert not any(w["code"] == "MISSING_UNIT" for w in r.advertencias)
    assert all(texto[c["start"] : c["end"]] == c["text"] for c in r.candidatos)
    assert r.propuesta.componentes == ()
    assert r.propuesta.color_principal["value"] == "blanco"
    evidencia = [c for c in r.candidatos if c["label"] == "MATERIAL"]
    assert len(evidencia) == 1 and evidencia[0]["text"] == material
    assert evidencia[0]["component_ref"] is None
    p = proyectar(r.resultado_original)
    assert r.resultado_original == original
    assert p["version_proyeccion"] == "PRF04_2"
    datos = p["especificacion"]["datos_tecnicos"]
    assert datos["descripcion_original"] == texto
    assert datos["componentes"] == []
    generales = datos["caracteristicas_generales"]
    assert generales["dimensiones"] == {
        "ancho": {"valor": "120", "unidad": "cm"},
        "profundidad": {"valor": "60", "unidad": "cm"},
        "alto": {"valor": "75", "unidad": "cm"},
    }
    atributos = {a["nombre"].lower(): a["valor"] for a in generales["atributos"]}
    assert atributos["material"] == material
    assert atributos["color"] == "blanco"
    assert not any(w["codigo"] in {"MISSING_UNIT", "CONFLICTING_VALUES"} for w in p["pendientes"])
    assert "schema_version" not in datos


def test_unidad_realmente_ausente_sigue_pendiente():
    r = AdaptadorNLP().extraer(
        solicitud_id="sin-unidad", texto="Un escritorio de 120 de ancho.", moneda="BOB"
    )
    p = proyectar(r.resultado_original)
    assert any(w["codigo"] == "MISSING_UNIT" for w in p["pendientes"])


def test_voz_real_unidad_del_alto_no_autoriza_ancho():
    texto = "Quiero un escritorio de 120 de ancho y 75 centímetros de alto"
    r = AdaptadorNLP().extraer(solicitud_id="voz-unidad", texto=texto, moneda="BOB")
    original = deepcopy(r.resultado_original)
    p = proyectar(original)
    dims = p["especificacion"]["datos_tecnicos"]["caracteristicas_generales"]["dimensiones"]
    assert dims == {"alto": {"valor": "75", "unidad": "cm"}}
    pendiente = next(w for w in p["pendientes"] if w["codigo"] == "MISSING_UNIT")
    assert pendiente["resolucion"] == {"tipo": "DIMENSION", "clave": "ancho"}
    assert r.resultado_original == original
    assert p["version_proyeccion"] == "PRF04_2"
    assert r.version_contrato == "1.0"


@pytest.mark.parametrize("material", ["melamine", "melamina"])
def test_voz_real_etapa_no_es_tapa_ni_espesor_de_cajones(material):
    texto = (
        f"Necesito un escritorio de {material} a blanca de 120 centímetros de ancho "
        "con 2 cajones y una etapa de 18 milímetros de espesor"
    )
    r = AdaptadorNLP().extraer(solicitud_id="voz-etapa", texto=texto, moneda="BOB")
    original = deepcopy(r.resultado_original)
    p = proyectar(original)
    datos = p["especificacion"]["datos_tecnicos"]
    assert datos["caracteristicas_generales"]["dimensiones"] == {
        "ancho": {"valor": "120", "unidad": "cm"}
    }
    assert len(datos["componentes"]) == 1
    cajones = datos["componentes"][0]
    assert cajones["nombre"] == "cajones"
    assert cajones["cantidad_interna"] == 2
    assert "espesor" not in cajones
    pendiente = next(w for w in p["pendientes"] if w["codigo"] == "ESPESOR_SIN_COMPONENTE")
    assert pendiente["resolucion"] == {"tipo": "ESPESOR_SIN_COMPONENTE", "valor": "18 mm"}
    assert not any(w["ruta"] == "/item_proposal/thicknesses" for w in p["pendientes"])
    assert r.resultado_original == original
    assert datos["descripcion_original"] == texto
