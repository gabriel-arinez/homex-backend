"""Postvalidation reviews describe the final proposal without losing source evidence."""

from copy import deepcopy

import pytest
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from apps.capturas import catalogo
from apps.capturas.models import Captura
from apps.capturas.pipeline import procesar_intento
from apps.catalogo.models import Producto
from tests.api.test_catalogo_captura import payload
from tests.factories import commercial_voice_text, valor

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def ctx(django_user_model):
    actor = django_user_model.objects.create_user(username="review-coherence")
    actor.groups.add(Group.objects.get_or_create(name="ENCARGADO_TIENDA")[0])
    api = APIClient()
    api.force_authenticate(actor)
    return actor, api


def capture_proposal(api, text):
    data = {**payload("OTRO"), "texto": commercial_voice_text(text)}
    response = api.post("/api/v1/capturas/catalogo/", data, format="json")
    assert response.status_code == 202, response.data
    assert procesar_intento(intento_id=response.data["intento_id"]) == "FINALIZADO"
    result = api.get(f"/api/v1/capturas/catalogo/{response.data['id']}/")
    assert result.status_code == 200, result.data
    return response.data["id"], result.data["propuesta"]


def assert_rejection(proposal, field):
    assert field not in proposal["fields"]
    evidence = [e for e in proposal["evidence"] if e["label"] == field]
    assert evidence and all(e["decision"] == "UNRESOLVED" for e in evidence)
    reviews = [r for r in proposal["field_reviews"] if r["field"] == field]
    assert reviews and all(r["code"] == "BACKEND_VALIDATION_REJECTED" for r in reviews)
    assert all(r["severity"] == "REVIEW" for r in reviews)
    assert any(r["message"] in proposal["warnings"] for r in reviews)
    assert {e["candidate_id"] for e in evidence} == {
        eid for r in reviews for eid in r["evidence_ids"]
    }
    assert all(e["reason"] == reviews[0]["message"] for e in evidence)
    return reviews[0]


def test_foreign_price_review_is_reclassified_with_stable_source_identity(ctx, monkeypatch):
    _, api = ctx
    original_extract = catalogo.extract_catalog
    extracted = []

    def record(request):
        result = original_extract(request)
        extracted.append(deepcopy(result.model_dump(mode="json")))
        return result

    monkeypatch.setattr(catalogo, "extract_catalog", record)
    _, proposal = capture_proposal(api, "producto: Zócalo Aurora; precio 45 dólares")
    review = assert_rejection(proposal, "precio_lista")
    old_review = next(r for r in extracted[0]["field_reviews"] if r["field"] == "precio_lista")
    assert review["review_id"] == old_review["review_id"]
    assert review["evidence_ids"] == old_review["evidence_ids"]
    for old in extracted[0]["evidence"]:
        new = next(e for e in proposal["evidence"] if e["candidate_id"] == old["candidate_id"])
        assert {k: new[k] for k in ("label", "start", "end", "text", "normalized_value")} == {
            k: old[k] for k in ("label", "start", "end", "text", "normalized_value")
        }
    assert "Precio dictado: sugerencia pendiente de revisión comercial." not in proposal["warnings"]
    assert not Producto.objects.exists()


@pytest.mark.parametrize("field", ["unidad_stock", "precio_lista"])
def test_other_postvalidation_drops_get_linked_review(ctx, monkeypatch, field):
    _, api = ctx
    original_extract = catalogo.extract_catalog

    def invalid_proposal(request):
        result = original_extract(request)
        # Keep real NLP IDs/spans; inject only a downstream-invalid normalized value.
        source = next(e for e in result.evidence if e.label == "precio_lista")
        invalid = valor("UNIDAD_MEDIDA", "M2").pk if field == "unidad_stock" else "1234567890123.00"
        result.fields.pop("precio_lista")
        result.field_reviews = []
        result.fields[field] = invalid
        source.label = field
        source.normalized_value = invalid
        return result

    monkeypatch.setattr(catalogo, "extract_catalog", invalid_proposal)
    _, proposal = capture_proposal(api, "producto: Zócalo Aurora; precio 45 bolivianos")
    assert_rejection(proposal, field)
    assert proposal["fields"]["nombre"] == "Zócalo Aurora"


@pytest.mark.parametrize("currency", ["bolivianos", "dólares"])
def test_final_price_review_can_be_saved_without_bypassing_provenance(ctx, currency):
    _, api = ctx
    capture_id, proposal = capture_proposal(api, f"producto: Zócalo Aurora; precio 45 {currency}")
    review = next(r for r in proposal["field_reviews"] if r["field"] == "precio_lista")
    accepted = currency == "bolivianos"
    assert ("precio_lista" in proposal["fields"]) is accepted
    assert (review["code"] == "COMMERCIAL_PRICE_REVIEW") is accepted
    assert (
        "Precio dictado: sugerencia pendiente de revisión comercial." in proposal["warnings"]
    ) is accepted
    decision = {
        "decision_id": "price-reviewed",
        "review_id": review["review_id"],
        "field": "precio_lista",
        "evidence_ids": review["evidence_ids"],
        "estado": "confirmado" if accepted else "corregido",
        "valor_original": "45.00" if accepted else None,
        "valor_final": "45.00",
    }
    data = {
        "sku": "COHERENCE-0130",
        "nombre": proposal["fields"]["nombre"],
        "categoria": valor("CATEGORIA_PRODUCTO", "OTRO").pk,
        "unidad_stock": valor("UNIDAD_MEDIDA", "PIEZA").pk,
        "precio_lista": "45.00",
        "revision_humana_voz": [{"captura_asistida_id": capture_id, "decisiones": [decision]}],
    }
    forged = deepcopy(data)
    forged["revision_humana_voz"][0]["decisiones"][0]["evidence_ids"] = ["forged"]
    assert api.post("/api/v1/catalogo/productos/", forged, format="json").status_code == 400
    if not accepted:
        # A discarded value is not an accepted field-level suggestion. Its
        # reclassified observation can be resolved only with the actual source.
        for update in ({"review_id": "field:precio_lista"}, {"valor_original": "45.00"}):
            forged = deepcopy(data)
            forged["revision_humana_voz"][0]["decisiones"][0].update(update)
            assert api.post("/api/v1/catalogo/productos/", forged, format="json").status_code == 400
    assert not Producto.objects.exists()
    response = api.post("/api/v1/catalogo/productos/", data, format="json")
    assert response.status_code == 201, response.data
    product = Producto.objects.get(pk=response.data["id"])
    assert product.revision_humana_voz[0]["decisiones"][0] == decision
    raw = Captura.objects.get(pk=capture_id).intentocaptura_set.get().resultado_raw
    assert raw["field_reviews"] == proposal["field_reviews"]
