"""Thickness claims are checked against the trusted pending and saved component."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from rest_framework.exceptions import ValidationError

from apps.capturas.models import Captura
from apps.capturas.revision_voz import validar_revision_voz


@pytest.fixture(autouse=True)
def catalogo_estructural():
    pass


@pytest.fixture(autouse=True)
def transiciones_pedido():
    pass


@pytest.fixture
def review(monkeypatch):
    pending = {
        "codigo": "ESPESOR_SIN_COMPONENTE",
        "ruta": "componentes",
        "mensaje": "Associate thickness",
        "resolucion": {"tipo": "ESPESOR_SIN_COMPONENTE", "valor": "18 mm"},
    }
    attempt = SimpleNamespace(
        pk=3,
        modelo_asr_version=None,
        estado="FINALIZADO",
        resultado_raw={"status": "REQUIRES_REVIEW"},
        proyeccion_configurador={"pendientes": [pending], "especificacion": {}},
    )
    capture = SimpleNamespace(
        pk=1,
        estado="COMPLETADA",
        captura_origen_id=None,
        vendedor_id=9,
        modo_captura="ASISTIDA_CREACION_MUEBLE",
        sesion_borrador=None,
        categoria_catalogo=None,
        moneda_contexto_codigo="BOB",
        proforma_id=None,
        intentocaptura_set=MagicMock(),
    )
    capture.intentocaptura_set.order_by.return_value.first.return_value = attempt
    query = MagicMock()
    query.filter.return_value.first.return_value = capture
    monkeypatch.setattr(Captura.objects, "select_for_update", lambda: query)
    # Use exactly the same serialized immutable pending as the validator.
    from apps.capturas.api.proyeccion_serializers import PendienteAsistidaSerializer

    pending = dict(PendienteAsistidaSerializer(pending).data)
    snapshot = {
        "captura_asistida_id": 1,
        "pendientes_originales": [pending],
        "asignaciones_espesor": [
            {
                "indice": 0,
                "componente_uid": "top",
                "pendiente_original": pending,
            }
        ],
        "decisiones": [],
    }

    def validate(value, *, state=None, previous=None, original="18 mm"):
        incoming = deepcopy(snapshot)
        if state:
            incoming["decisiones"] = [
                {
                    "decision_id": f"thickness-{value}-{state}",
                    "review_id": "pending:0",
                    "field": "componentes.top.espesor",
                    "evidence_ids": [],
                    "estado": state,
                    "valor_original": original,
                    "valor_final": value,
                }
            ]
        return validar_revision_voz(
            incoming=[incoming],
            previous=previous,
            actor=SimpleNamespace(pk=9),
            mode="ASISTIDA_CREACION_MUEBLE",
            final={"componentes": [{"uid": "top", "espesor": value}]},
        )

    return validate


@pytest.mark.parametrize("value", ["25 mm", "", "unknown", "-18 mm"])
def test_rejects_assignment_of_different_or_invalid_thickness(review, value):
    with pytest.raises(ValidationError):
        review(value)


@pytest.mark.parametrize("value", ["18 mm", "1.8 cm", "0,018 m", "18.000 milímetros"])
def test_accepts_equivalent_assignment_and_confirmed_decision(review, value):
    assert review(value)
    assert review(value, state="confirmado")


def test_correction_requires_explicit_trusted_human_decision(review):
    with pytest.raises(ValidationError):
        review("25 mm", state="confirmado")
    saved = review("25 mm", state="corregido")
    assert saved[0]["decisiones"][0]["valor_original"] == "18 mm"
    assert saved[0]["decisiones"][0]["valor_final"] == "25 mm"
    assert review("25 mm", state="corregido", previous=saved) == saved
    with pytest.raises(ValidationError):
        review("25 mm", state="corregido", original="17 mm")
