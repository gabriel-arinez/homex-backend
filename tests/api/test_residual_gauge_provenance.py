"""Contextual gauge suggestions must not claim an explicitly shared unit."""

import pytest

from tests.api.test_final_inferred_projection import (
    partial_api,  # noqa: F401
    review,
)

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize(
    "text,value",
    [
        ("una mesa con tablero MDF de 15", "15 mm"),
        ("una mesa de melamina de dieciocho de espesor", "18 mm"),
    ],
)
def test_contextual_gauge_message_preserves_inferred_provenance(intake, text, value):
    result = review(intake, text)
    pending = next(
        p
        for p in result["propuesta_configurador"]["pendientes"]
        if p.get("resolucion") == {"tipo": "ESPESOR_SIN_COMPONENTE", "valor": value}
    )
    assert "inferida" in pending["mensaje"].lower()
    assert "compartida por enumeración" not in pending["mensaje"].lower()
    assert any(
        c["decision"] == "UNRESOLVED"
        and isinstance(c["normalized_value"], dict)
        and c["normalized_value"].get("unit_inferred")
        for c in result["candidatos"]
    )
