"""RED/GREEN regression tests for residual UX review persistence and warning hygiene."""

from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from apps.capturas.pipeline import procesar_intento
from apps.capturas.proyeccion_prf03 import proyectar
from apps.proformas.models import DetalleProforma
from tests.api.test_ap3_proformas_integrales import payload_integral
from tests.api.test_final_inferred_projection import entry, review
from tests.factories import vendedor

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(name="intake")
def residual_ux_api(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ux-residual-review"))
    api = APIClient()
    api.force_authenticate(actor)
    return api


def test_geometria_uses_observaciones_route_and_persists_individual_observaciones(intake):
    text = "Un escritorio en L de 160 por 80, madera enchapada con acabado de poliuretano."
    data = entry(text)
    received = intake.post("/api/v1/capturas/asistidas/", data, format="json")
    assert received.status_code == 202, received.data
    assert procesar_intento(intento_id=received.data["intento_id"]) == "FINALIZADO"
    capture = intake.get(f"/api/v1/capturas/asistidas/{received.data['id']}/").data
    proposal = capture["propuesta_configurador"]

    geom = next(p for p in proposal["pendientes"] if p["codigo"] == "GEOMETRIA")
    assert geom["ruta"] == "especificacion.observaciones"
    assert geom["resolucion"] == {"tipo": "OBSERVACIONES"}

    obs_pendings = [
        (i, p)
        for i, p in enumerate(proposal["pendientes"])
        if (p.get("resolucion") or {}).get("tipo") == "OBSERVACIONES"
    ]
    assert len(obs_pendings) >= 2
    orig_obs = proposal["especificacion"]["observaciones"]
    final_obs = f"{orig_obs or ''} — confirmado en L".strip(" —")

    payload = payload_integral(clave=uuid4())
    payload["sesion_borrador"] = data["sesion_borrador"]
    line = payload["detalles"][0]
    line["captura_asistida_id"] = capture["id"]
    line["nombre"] = proposal["comercial"]["nombre"]
    line["cantidad"] = 1
    line["precio_unitario"] = "1500.00"
    line["especificacion"] = {
        **proposal["especificacion"],
        "observaciones": final_obs,
        "datos_tecnicos": {
            **proposal["especificacion"]["datos_tecnicos"],
            "caracteristicas_generales": {
                "dimensiones": {
                    "largo": {"valor": "160", "unidad": "cm"},
                    "ancho": {"valor": "80", "unidad": "cm"},
                }
            },
            "revision_humana_voz": [
                {
                    "captura_asistida_id": capture["id"],
                    "pendientes_originales": proposal["pendientes"],
                    "asignaciones_espesor": [],
                    "descartes": [],
                    "decisiones": [
                        {
                            "decision_id": f"ux-obs-{obs_pendings[0][0]}",
                            "review_id": f"pending:{obs_pendings[0][0]}",
                            "field": "observaciones",
                            "evidence_ids": [],
                            "estado": "corregido",
                            "valor_original": orig_obs,
                            "valor_final": final_obs,
                        }
                    ],
                }
            ],
        },
    }
    created = intake.post("/api/v1/proformas/integral/", payload, format="json")
    assert created.status_code == 201, created.data
    detalle = DetalleProforma.objects.get(proforma_id=created.data["id"])
    assert detalle.especificacionmueble.observaciones == final_obs


def test_lexical_recovery_binds_to_actual_target_not_component_material(intake):
    proposal = review(intake, "un gadetero con tablero de melamina")["propuesta_configurador"]
    rec = next(p for p in proposal["pendientes"] if p["codigo"] == "RECUPERACION_LEXICA")
    assert rec["ruta"] != "pieza-1.material"
    assert (rec.get("resolucion") or {}).get("campo") != "material"


def test_humanize_warning_never_passes_raw_english_internal_messages():
    raw = {
        "schema_version": "1.0",
        "request_id": "raw-warn-01",
        "status": "REQUIRES_REVIEW",
        "proposed_item_count": 1,
        "engine": {"mode": "RULES_ONLY", "rules_version": "prf04-rules-context-5"},
        "text_original": "Una mesa de 120 cm.",
        "item_proposal": {
            "item_type": "MUEBLE_MEDIDA",
            "name": "mesa",
            "quantity": 1,
            "dimensions": [
                {
                    "value": "120",
                    "unit": "cm",
                    "axis": "ancho",
                    "original_text": "120 cm",
                    "value_mm": "1200",
                    "evidence_ids": [],
                }
            ],
            "thicknesses": [],
            "components": [],
            "accessories": [],
            "unresolved": [],
        },
        "candidates": [],
        "warnings": [
            {
                "code": "CONFLICTING_VALUES",
                "path": "/item_proposal/dimensions",
                "severity": "REVIEW",
                "message": "Internal parser diagnostic: UNRESOLVED component_ref mismatch.",
            }
        ],
    }
    proy = proyectar(raw)
    assert proy is not None
    for p in proy["pendientes"]:
        assert "UNRESOLVED" not in p["mensaje"]
        assert "component_ref" not in p["mensaje"]
        assert "Internal parser" not in p["mensaje"]
