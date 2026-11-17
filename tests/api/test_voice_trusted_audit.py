"""Browser audit is a claim; persisted attempts remain authoritative."""

from copy import deepcopy
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from apps.capturas.models import Captura, RevisionAsistida
from apps.capturas.pipeline import procesar_intento
from apps.proformas.models import EspecificacionMueble, Proforma
from tests.api.test_ap3_proformas_integrales import payload_integral
from tests.factories import vendedor

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def case(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="trusted-audit"))
    api = APIClient()
    api.force_authenticate(actor)
    session = str(uuid4())
    capture = api.post(
        "/api/v1/capturas/asistidas/",
        {
            "clave_idempotencia": str(uuid4()),
            "sesion_borrador": session,
            "moneda_codigo": "BOB",
            "texto": "un escritorio, total 100 bolivianos",
        },
        format="json",
    )
    assert capture.status_code == 202
    assert procesar_intento(intento_id=capture.data["intento_id"]) == "FINALIZADO"
    proposal = api.get(f"/api/v1/capturas/asistidas/{capture.data['id']}/").data[
        "propuesta_configurador"
    ]
    payload = payload_integral(clave=uuid4())
    payload["sesion_borrador"] = session
    line = payload["detalles"][0]
    line["captura_asistida_id"] = capture.data["id"]
    audit = {
        "captura_asistida_id": capture.data["id"],
        "pendientes_originales": proposal["pendientes"],
        "asignaciones_espesor": [],
        "descartes": [],
    }
    line["especificacion"]["datos_tecnicos"]["revision_humana_voz"] = [audit]
    return actor, api, payload, audit


@pytest.mark.parametrize("forgery", ["pending", "capture", "session", "shape"])
def test_rejects_forged_audit_atomically(case, forgery):
    _, api, payload, audit = case
    if forgery == "pending":
        audit["pendientes_originales"][0]["mensaje"] = "invented browser evidence"
    elif forgery == "capture":
        audit["captura_asistida_id"] += 999
    elif forgery == "session":
        payload["sesion_borrador"] = str(uuid4())
    else:
        audit["descartes"] = [
            {"indice": 0, "pendiente_original": audit["pendientes_originales"][0], "motivo": ""}
        ]
    response = api.post("/api/v1/proformas/integral/", payload, format="json")
    assert response.status_code in {400, 409}, response.data
    assert not Proforma.objects.exists()
    assert not RevisionAsistida.objects.exists()


def test_save_retries_deduplicate_and_preserve_immutable_initial_review(case):
    _, api, payload, audit = case
    response = api.post("/api/v1/proformas/integral/", payload, format="json")
    assert response.status_code == 201, response.data
    ficha = EspecificacionMueble.objects.get()
    original = deepcopy(RevisionAsistida.objects.get().resultado_humano)
    from apps.proformas.services import actualizar_especificacion

    data = deepcopy(ficha.datos_tecnicos)
    data["revision_humana_voz"] = [audit, audit]
    actualizar_especificacion(
        detalle_id=ficha.proforma_detalle_id, actor=case[0], datos_tecnicos=data
    )
    ficha.refresh_from_db()
    assert len(ficha.datos_tecnicos["revision_humana_voz"]) == 1
    data["revision_humana_voz"] = []
    actualizar_especificacion(
        detalle_id=ficha.proforma_detalle_id, actor=case[0], datos_tecnicos=data
    )
    ficha.refresh_from_db()
    assert len(ficha.datos_tecnicos["revision_humana_voz"]) == 1
    assert RevisionAsistida.objects.get().resultado_humano == original
    assert (
        Captura.objects.get(pk=audit["captura_asistida_id"]).proforma_detalle_id
        == ficha.proforma_detalle_id
    )


def test_new_decisions_use_trusted_original_final_and_evidence(case):
    actor, api, payload, audit = case
    i = next(
        i for i, p in enumerate(audit["pendientes_originales"]) if p["codigo"] == "TOTAL_NEGOCIADO"
    )
    decision = {
        "decision_id": "price-correction-1",
        "review_id": f"pending:{i}",
        "field": "precio_unitario",
        "evidence_ids": [],
        "estado": "corregido",
        "valor_original": None,
        "valor_final": "2500.00",
    }
    audit["decisiones"] = [decision]
    response = api.post("/api/v1/proformas/integral/", payload, format="json")
    assert response.status_code == 201, response.data
    from apps.proformas.services import actualizar_especificacion

    ficha = EspecificacionMueble.objects.get()
    initial = deepcopy(ficha.datos_tecnicos)
    later = deepcopy(initial)
    later["revision_humana_voz"][0]["decisiones"][0]["valor_final"] = "999"
    with pytest.raises(Exception) as caught:
        actualizar_especificacion(
            detalle_id=ficha.proforma_detalle_id, actor=actor, datos_tecnicos=later
        )
    assert "histórica" in str(caught.value)
    ficha.refresh_from_db()
    assert ficha.datos_tecnicos == initial
    actualizar_especificacion(
        detalle_id=ficha.proforma_detalle_id, actor=actor, datos_tecnicos=deepcopy(initial)
    )
    ficha.refresh_from_db()
    assert ficha.datos_tecnicos == initial


@pytest.mark.parametrize(
    "key,value",
    [
        ("evidence_ids", ["forged"]),
        ("field", "cantidad"),
        ("valor_original", "100"),
        ("valor_final", "wrong"),
        ("review_id", "pending:999"),
    ],
)
def test_forged_general_decision_is_rejected(case, key, value):
    _, api, payload, audit = case
    i = next(
        i for i, p in enumerate(audit["pendientes_originales"]) if p["codigo"] == "TOTAL_NEGOCIADO"
    )
    audit["decisiones"] = [
        {
            "decision_id": "forged",
            "review_id": f"pending:{i}",
            "field": "precio_unitario",
            "evidence_ids": [],
            "estado": "corregido",
            "valor_original": None,
            "valor_final": "2500.00",
        }
        | {key: value}
    ]
    response = api.post("/api/v1/proformas/integral/", payload, format="json")
    assert response.status_code == 400, response.data
    assert not Proforma.objects.exists()


@pytest.fixture
def catalog_case(django_user_model):
    from tests.factories import valor

    actor = vendedor(django_user_model.objects.create_user(username="catalog-audit"))
    api = APIClient()
    api.force_authenticate(actor)
    capture = api.post(
        "/api/v1/capturas/catalogo/",
        {
            "clave_idempotencia": str(uuid4()),
            "sesion_borrador": str(uuid4()),
            "categoria": "OTRO",
            "texto": "producto: Zócalo Aurora, precio 45 bolivianos",
        },
        format="json",
    )
    assert capture.status_code == 202, capture.data
    assert procesar_intento(intento_id=capture.data["intento_id"]) == "FINALIZADO"
    raw = Captura.objects.get(pk=capture.data["id"]).intentocaptura_set.get().resultado_raw
    review = next(r for r in raw["field_reviews"] if r["field"] == "precio_lista")
    event = {
        "decision_id": "catalog-price-1",
        "review_id": review["review_id"],
        "field": "precio_lista",
        "evidence_ids": review["evidence_ids"],
        "estado": "confirmado",
        "valor_original": "45.00",
        "valor_final": "45.00",
    }
    payload = {
        "sku": "AUDIT-NEW",
        "nombre": "Zócalo Aurora",
        "categoria": valor("CATEGORIA_PRODUCTO", "OTRO").pk,
        "unidad_stock": valor("UNIDAD_MEDIDA", "PIEZA").pk,
        "precio_lista": "45.00",
        "revision_humana_voz": [{"captura_asistida_id": capture.data["id"], "decisiones": [event]}],
    }
    return actor, api, payload


def test_catalog_review_is_persisted_idempotent_append_only(catalog_case):
    from apps.catalogo.models import Producto
    from apps.catalogo.revision import revision_producto

    _, api, payload = catalog_case
    response = api.post("/api/v1/catalogo/productos/", payload, format="json")
    assert response.status_code == 201, response.data
    product = Producto.objects.get(pk=response.data["id"])
    original = deepcopy(product.revision_humana_voz)
    url = f"/api/v1/catalogo/productos/{product.pk}/"
    for _ in range(2):
        response = api.patch(url, payload, format="json", HTTP_IF_MATCH=revision_producto(product))
        assert response.status_code == 200, response.data
        product.refresh_from_db()
        assert product.revision_humana_voz == original
    event = deepcopy(original[0]["decisiones"][0])
    event.update(decision_id="catalog-price-2", estado="corregido", valor_final="50.00")
    payload["precio_lista"] = "50.00"
    payload["revision_humana_voz"] = [
        original[0],
        {"captura_asistida_id": original[0]["captura_asistida_id"], "decisiones": [event]},
    ]
    response = api.patch(url, payload, format="json", HTTP_IF_MATCH=revision_producto(product))
    assert response.status_code == 200, response.data
    product.refresh_from_db()
    assert len(product.revision_humana_voz) == 2
    assert product.revision_humana_voz[0] == original[0]


@pytest.mark.parametrize("forgery", ["evidence", "owner", "category", "reuse"])
def test_catalog_audit_rejects_forged_provenance(catalog_case, django_user_model, forgery):
    from apps.catalogo.models import Producto
    from tests.factories import valor

    _, api, payload = catalog_case
    if forgery == "evidence":
        payload["revision_humana_voz"][0]["decisiones"][0]["evidence_ids"] = ["fake"]
    elif forgery == "owner":
        api.force_authenticate(
            vendedor(django_user_model.objects.create_user(username="other-owner"))
        )
    elif forgery == "category":
        payload["categoria"] = valor("CATEGORIA_PRODUCTO", "SILLA").pk
        payload["silla"] = {}
    else:
        assert api.post("/api/v1/catalogo/productos/", payload, format="json").status_code == 201
        payload["sku"] = "SECOND-AUDIT"
    before = Producto.objects.count()
    response = api.post("/api/v1/catalogo/productos/", payload, format="json")
    assert response.status_code == 400, response.data
    assert Producto.objects.count() == before


def test_generic_suggestion_and_later_commercial_edit_validate_same_save(case):
    _, api, payload, audit = case
    audit["decisiones"] = [
        {
            "decision_id": "quantity-confirm",
            "review_id": "field:cantidad",
            "field": "cantidad",
            "evidence_ids": [],
            "estado": "confirmado",
            "valor_original": 1,
            "valor_final": "1.0000",
        }
    ]
    response = api.post("/api/v1/proformas/integral/", payload, format="json")
    assert response.status_code == 201, response.data
    original = deepcopy(EspecificacionMueble.objects.get().datos_tecnicos["revision_humana_voz"])
    later = deepcopy(payload)
    later["clave_idempotencia"] = str(uuid4())
    later["cliente_nuevo"] = None
    later["cliente"] = response.data["cliente"]
    later["revision_esperada"] = response.data["revision"]
    line = later["detalles"][0]
    line.pop("captura_asistida_id")
    line["id"] = response.data["detalles"][0]["id"]
    line["cantidad"] = "2.0000"
    event = deepcopy(audit["decisiones"][0])
    event.update(decision_id="quantity-correct", estado="corregido", valor_final="2.0000")
    line["especificacion"]["datos_tecnicos"]["revision_humana_voz"] = original + [
        {
            "captura_asistida_id": audit["captura_asistida_id"],
            "pendientes_originales": audit["pendientes_originales"],
            "decisiones": [event],
        }
    ]
    updated = api.put(f"/api/v1/proformas/{response.data['id']}/integral/", later, format="json")
    assert updated.status_code == 200, updated.data
    ficha = EspecificacionMueble.objects.get()
    assert ficha.datos_tecnicos["revision_humana_voz"][0] == original[0]
    assert (
        ficha.datos_tecnicos["revision_humana_voz"][-1]["decisiones"][0]["valor_final"] == "2.0000"
    )
    assert RevisionAsistida.objects.count() == 1


def test_catalog_field_reviews_are_visible_through_public_contract(catalog_case):
    _, api, payload = catalog_case
    capture_id = payload["revision_humana_voz"][0]["captura_asistida_id"]
    response = api.get(f"/api/v1/capturas/catalogo/{capture_id}/")
    assert response.status_code == 200
    proposal = response.data["propuesta"]
    review = next(r for r in proposal["field_reviews"] if r["field"] == "precio_lista")
    assert review["severity"] == "REVIEW"
    assert set(review["evidence_ids"]) <= {e["candidate_id"] for e in proposal["evidence"]}


def test_catalog_multiple_human_transitions_before_save_validate_latest(catalog_case):
    from apps.catalogo.models import Producto

    _, api, payload = catalog_case
    first = deepcopy(payload["revision_humana_voz"][0])
    second = deepcopy(first)
    second["decisiones"][0].update(
        decision_id="pre-save-correction", estado="corregido", valor_final="50.00"
    )
    payload["revision_humana_voz"] = [first, second]
    payload["precio_lista"] = "50.00"
    response = api.post("/api/v1/catalogo/productos/", payload, format="json")
    assert response.status_code == 201, response.data
    history = Producto.objects.get(pk=response.data["id"]).revision_humana_voz
    assert [row["decisiones"][0]["valor_final"] for row in history] == ["45.00", "50.00"]


def test_catalog_nested_leaf_audit_uses_real_evidence_and_saved_scalar(catalog_case):
    from apps.catalogo.models import Producto
    from tests.factories import valor

    _, api, payload = catalog_case
    capture = api.post(
        "/api/v1/capturas/catalogo/",
        {
            "clave_idempotencia": str(uuid4()),
            "sesion_borrador": str(uuid4()),
            "categoria": "SILLA",
            "texto": "nombre: Silla Aurora; respaldo de malla; precio 45 bolivianos",
        },
        format="json",
    )
    assert capture.status_code == 202
    assert procesar_intento(intento_id=capture.data["intento_id"]) == "FINALIZADO"
    proposal = api.get(f"/api/v1/capturas/catalogo/{capture.data['id']}/").data["propuesta"]
    field = "especificaciones.material_respaldo"
    evidence = [
        e["candidate_id"]
        for e in proposal["evidence"]
        if e["label"] == field and e["decision"] == "ACCEPTED"
    ]
    assert evidence
    original = proposal["fields"]["especificaciones"]["material_respaldo"]
    payload.update(
        categoria=valor("CATEGORIA_PRODUCTO", "SILLA").pk,
        nombre="Silla Aurora",
        silla={"especificaciones": {"material_respaldo": "PVC"}},
    )
    payload["revision_humana_voz"] = [
        {
            "captura_asistida_id": capture.data["id"],
            "decisiones": [
                {
                    "decision_id": "nested-correction",
                    "review_id": "field:" + field,
                    "field": field,
                    "evidence_ids": evidence,
                    "estado": "corregido",
                    "valor_original": original,
                    "valor_final": "PVC",
                }
            ],
        }
    ]
    response = api.post("/api/v1/catalogo/productos/", payload, format="json")
    assert response.status_code == 201, response.data
    product = Producto.objects.get(pk=response.data["id"])
    event = product.revision_humana_voz[0]["decisiones"][0]
    assert event["field"] == field and event["evidence_ids"] == evidence
    assert (
        event["valor_final"] == product.productosilla.especificaciones["material_respaldo"] == "PVC"
    )


def test_floor_and_common_note_reviews_validate_actual_persisted_values(catalog_case):
    from apps.catalogo.models import Producto
    from tests.factories import valor

    _, api, payload = catalog_case
    capture = api.post(
        "/api/v1/capturas/catalogo/",
        {
            "clave_idempotencia": str(uuid4()),
            "sesion_borrador": str(uuid4()),
            "categoria": "PISO_FLOTANTE",
            "texto": (
                "nombre: Piso Aurora; espesor 8 mm; precio 45 bolivianos; "
                "observaciones: uso residencial"
            ),
        },
        format="json",
    )
    assert capture.status_code == 202
    assert procesar_intento(intento_id=capture.data["intento_id"]) == "FINALIZADO"
    proposal = api.get(f"/api/v1/capturas/catalogo/{capture.data['id']}/").data["propuesta"]
    fields = proposal["fields"]
    assert fields["observaciones"] and fields["espesor_mm"]
    payload.update(
        categoria=valor("CATEGORIA_PRODUCTO", "PISO_FLOTANTE").pk,
        unidad_stock=valor("UNIDAD_MEDIDA", "M2").pk,
        nombre=fields["nombre"],
        observaciones=fields["observaciones"],
        piso={"espesor_mm": "8.00"},
    )
    payload["revision_humana_voz"] = [
        {
            "captura_asistida_id": capture.data["id"],
            "decisiones": [
                {
                    "decision_id": f"floor-{field}",
                    "review_id": f"field:{field}",
                    "field": field,
                    "evidence_ids": [
                        e["candidate_id"]
                        for e in proposal["evidence"]
                        if e["label"] == field and e["decision"] == "ACCEPTED"
                    ],
                    "estado": "confirmado",
                    "valor_original": fields[field],
                    "valor_final": "8.00" if field == "espesor_mm" else fields[field],
                }
                for field in ("observaciones", "espesor_mm")
            ],
        }
    ]
    response = api.post("/api/v1/catalogo/productos/", payload, format="json")
    assert response.status_code == 201, response.data
    product = Producto.objects.get(pk=response.data["id"])
    assert product.observaciones == fields["observaciones"]
    assert str(product.productopiso.espesor_mm) == "8.00"
    assert len(product.revision_humana_voz[0]["decisiones"]) == 2


def test_catalog_review_preserves_existing_zero_price_manual_policy(catalog_case):
    _, api, payload = catalog_case
    manual = deepcopy(payload)
    manual.pop("revision_humana_voz")
    manual.update(sku="MANUAL-ZERO", precio_lista="0.00")
    manual_response = api.post("/api/v1/catalogo/productos/", manual, format="json")
    assert manual_response.status_code == 201, manual_response.data
    payload.update(sku="AUDITED-ZERO", precio_lista="0.00")
    event = payload["revision_humana_voz"][0]["decisiones"][0]
    event.update(decision_id="zero-price-correction", estado="corregido", valor_final="0.00")
    audited = api.post("/api/v1/catalogo/productos/", payload, format="json")
    assert audited.status_code == 201, audited.data
    assert audited.data["precio_lista"] == "0.00"


def test_voice_review_preserves_supported_manual_inch_dimensions(case):
    _, api, payload, _ = case
    capture = api.post(
        "/api/v1/capturas/asistidas/",
        {
            "clave_idempotencia": str(uuid4()),
            "sesion_borrador": payload["sesion_borrador"],
            "moneda_codigo": "BOB",
            "texto": "un escritorio de 100 cm de ancho, precio unitario 100 bolivianos",
        },
        format="json",
    )
    assert capture.status_code == 202
    assert procesar_intento(intento_id=capture.data["intento_id"]) == "FINALIZADO"
    proposal = api.get(f"/api/v1/capturas/asistidas/{capture.data['id']}/").data[
        "propuesta_configurador"
    ]
    technical = proposal["especificacion"]["datos_tecnicos"]
    dimensions = technical.get("caracteristicas_generales", {}).get(
        "dimensiones", technical.get("dimensiones", {})
    )
    assert dimensions.get("ancho")
    line = payload["detalles"][0]
    data = line["especificacion"]["datos_tecnicos"]
    data.setdefault("caracteristicas_generales", {}).setdefault("dimensiones", {})["ancho"] = {
        "valor": "4",
        "unidad": "pulgadas",
    }
    manual = deepcopy(payload)
    manual["clave_idempotencia"] = str(uuid4())
    manual["detalles"][0].pop("captura_asistida_id")
    manual["detalles"][0]["especificacion"]["datos_tecnicos"].pop("revision_humana_voz")
    manual_result = api.post("/api/v1/proformas/integral/", manual, format="json")
    assert manual_result.status_code == 201, manual_result.data
    line["captura_asistida_id"] = capture.data["id"]
    data["revision_humana_voz"] = [
        {
            "captura_asistida_id": capture.data["id"],
            "pendientes_originales": proposal["pendientes"],
            "decisiones": [
                {
                    "decision_id": "inch-dimension",
                    "review_id": "field:dimensiones.ancho",
                    "field": "dimensiones.ancho",
                    "evidence_ids": [],
                    "estado": "corregido",
                    "valor_original": dimensions["ancho"],
                    "valor_final": {"valor": "4", "unidad": "pulgadas"},
                }
            ],
        }
    ]
    reviewed = api.post("/api/v1/proformas/integral/", payload, format="json")
    assert reviewed.status_code == 201, reviewed.data
