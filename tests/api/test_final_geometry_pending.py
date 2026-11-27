"""Axisless geometry remains actionable through the public capture review route."""

import pytest
from rest_framework.test import APIClient

from apps.clientes.models import Cliente
from apps.proformas.models import DetalleProforma, Proforma
from tests.api.test_final_inferred_projection import review
from tests.factories import vendedor

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(name="intake")
def geometry_api(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="geometry-review"))
    api = APIClient()
    api.force_authenticate(actor)
    return api


@pytest.mark.parametrize(
    "text,values",
    [
        ("Dos escritorios en L de 150x150, total 800 bolivianos", ("150", "150")),
        ("Un escritorio en L de 160 por 80", ("160", "80")),
        ("Un escritorio en L de 170 × 90 cm", ("170", "90")),
    ],
)
def test_l_arms_keep_one_complete_axis_review_without_inventing_axes(intake, text, values):
    result = review(intake, text)
    proposal = result["propuesta_configurador"]
    general = proposal["especificacion"]["datos_tecnicos"]["caracteristicas_generales"]
    assert not general.get("dimensiones")
    pending = [p for p in proposal["pendientes"] if p["codigo"] == "MISSING_AXIS"]
    assert len(pending) == 1
    assert pending[0]["resolucion"] == {"tipo": "DIMENSIONES_NUEVAS", "cantidad": 2}
    assert all(value in pending[0]["mensaje"] for value in values)
    assert any(p["codigo"] == "GEOMETRIA" for p in proposal["pendientes"])
    assert any(c["label"] == "GEOMETRIA" for c in result["candidatos"])
    assert not Proforma.objects.exists()
    assert not DetalleProforma.objects.exists()
    assert not Cliente.objects.exists()
