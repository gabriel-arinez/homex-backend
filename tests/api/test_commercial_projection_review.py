"""Legacy review must retain the persisted, scoped commercial proposal."""

from copy import deepcopy
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from apps.capturas.models import IntentoCaptura, ItemIA
from apps.capturas.nlp.adapter import AdaptadorNLP
from apps.proformas.services import crear_proforma
from tests.factories import cliente_persona, vendedor


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("kind", ["explicit", "total", "historical", "malformed"])
def test_public_review_projects_same_attempt_without_rewriting_legacy_evidence(
    django_user_model, kind
):
    actor = vendedor(django_user_model.objects.create_user(username="scoped-review"))
    quote = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    client = APIClient()
    client.force_authenticate(actor)
    text = (
        "Dos escritorios de 160 cm de ancho. Credencia integrada de MDF "
        "de 110 cm de ancho, 65 cm de alto y 45 de profundidad. "
        + (
            "Total negociado 3800 bolivianos."
            if kind == "total"
            else "Precio unitario 1900 bolivianos."
        )
    )
    created = client.post(
        "/api/v1/capturas/",
        {"clave_idempotencia": str(uuid4()), "proforma": quote.id, "texto": text},
        format="json",
    )
    assert created.status_code == 202
    attempt = IntentoCaptura.objects.get(pk=created.data["intento_id"])
    raw = (
        AdaptadorNLP()
        .extraer(solicitud_id="scoped-review", texto=text, moneda="BOB")
        .resultado_original
    )
    attempt.resultado_raw = (
        None if kind == "historical" else {"invalid": True} if kind == "malformed" else raw
    )
    attempt.estado = "FINALIZADO"
    attempt.save()
    if kind != "historical":
        item = ItemIA.objects.create(
            intento=attempt,
            nombre="Escritorios",
            cantidad=2,
            dimensiones={"ancho": "160 cm; 110 cm"},
            precio_total="3800",
        )
    snapshot = deepcopy(attempt.resultado_raw)
    response = client.get(f"/api/v1/capturas/{created.data['id']}/")
    assert response.status_code == 200
    if kind == "historical":
        assert response.data["item_ia"] is None
    else:
        assert response.data["item_ia"]["dimensiones"] == item.dimensiones
        assert response.data["item_ia"]["precio_total"] == "3800.00"
    projection = response.data["proyeccion_configurador"]
    assert response.data["proyeccion_error"] is (kind == "malformed")
    if kind in {"historical", "malformed"}:
        assert projection is None
    else:
        technical = projection["especificacion"]["datos_tecnicos"]
        component = next(
            c for c in technical["componentes"] if c["nombre"].lower() == "credencia integrada"
        )
        assert "110 cm" in component["dimensiones"] and "65 cm" in component["dimensiones"]
        assert "45" not in component["dimensiones"]
        assert technical["caracteristicas_generales"]["dimensiones"]["ancho"] == {
            "valor": "160",
            "unidad": "cm",
        }
        assert any(p["codigo"] == "MISSING_UNIT" for p in projection["pendientes"])
        assert projection["comercial"]["precio_unitario"] == (
            "1900.00" if kind == "explicit" else None
        )
    attempt.refresh_from_db()
    quote.refresh_from_db()
    assert attempt.resultado_raw == snapshot
    assert quote.estado.codigo == "BORRADOR"
    assert not quote.detalles.exists()
