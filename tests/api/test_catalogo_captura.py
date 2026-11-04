from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.capturas.models import Captura, ItemIA, TrabajoOutbox
from apps.capturas.pipeline import procesar_intento
from apps.catalogo.models import Producto
from tests.factories import valor, vendedor

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def ctx(django_user_model):
    actor = django_user_model.objects.create_user(username="encargado")
    actor.groups.add(Group.objects.get_or_create(name="ENCARGADO_TIENDA")[0])
    client = APIClient()
    client.force_authenticate(actor)
    return actor, client


def payload(category="SILLA", **kw):
    return dict(
        clave_idempotencia=str(uuid4()),
        sesion_borrador=str(uuid4()),
        categoria=category,
        texto="nombre: Silla B15b; modelo: B15b; malla",
        **kw,
    )


@pytest.mark.parametrize("category", ["SILLA", "PISO_FLOTANTE", "OTRO"])
def test_proposal_no_commercial_writes_and_manual_create(ctx, category):
    actor, api = ctx
    data = payload(category)
    response = api.post("/api/v1/capturas/catalogo/", data, format="json")
    assert response.status_code == 202, response.data
    assert TrabajoOutbox.objects.filter(intento_id=response.data["intento_id"]).exists()
    assert procesar_intento(intento_id=response.data["intento_id"]) == "FINALIZADO"
    result = api.get(f"/api/v1/capturas/catalogo/{response.data['id']}/").data
    assert result["categoria"] == category
    assert result["texto_transcrito_original"] == data["texto"]
    assert result["propuesta"]["fields"]["nombre"] == "Silla B15b"
    assert not Producto.objects.exists()
    assert not ItemIA.objects.exists()
    fields = result["propuesta"]["fields"]
    unit = valor("UNIDAD_MEDIDA", "M2" if category == "PISO_FLOTANTE" else "PIEZA")
    manual = dict(
        categoria=valor("CATEGORIA_PRODUCTO", category).id,
        nombre=fields["nombre"],
        sku="MANUAL-" + category,
        unidad_stock=unit.id,
        precio_lista="100",
    )
    if category != "OTRO":
        manual["silla" if category == "SILLA" else "piso"] = {
            k: v
            for k, v in fields.items()
            if k not in {"nombre", "observaciones", "precio_lista", "unidad_stock"}
        }
    response = api.post("/api/v1/catalogo/productos/", manual, format="json")
    assert response.status_code == 201, response.data
    assert Producto.objects.get().stock == 0
    # No general administrator privileges.
    assert api.delete(f"/api/v1/catalogo/productos/{response.data['id']}/").status_code == 403


def test_idempotency_category_and_origin_isolation(ctx):
    _, api = ctx
    data = payload()
    first = api.post("/api/v1/capturas/catalogo/", data, format="json")
    assert first.status_code == 202
    assert api.post("/api/v1/capturas/catalogo/", data, format="json").data["reutilizada"]
    changed = {**data, "categoria": "OTRO"}
    assert api.post("/api/v1/capturas/catalogo/", changed, format="json").status_code == 409
    changed["clave_idempotencia"] = str(uuid4())
    assert api.post("/api/v1/capturas/catalogo/", changed, format="json").status_code == 400
    assert api.get(f"/api/v1/capturas/asistidas/{first.data['id']}/").status_code in {403, 404}
    origin = {**payload(), "captura_origen": first.data["id"], "categoria": "OTRO"}
    assert api.post("/api/v1/capturas/catalogo/", origin, format="json").status_code in {403, 404}


def test_inactive_category_and_permission(ctx, django_user_model):
    _, api = ctx
    category = valor("CATEGORIA_PRODUCTO", "SILLA")
    category.activo = False
    category.save()
    assert api.post("/api/v1/capturas/catalogo/", payload(), format="json").status_code == 400
    api.force_authenticate(vendedor(django_user_model.objects.create_user(username="seller")))
    assert api.post("/api/v1/capturas/catalogo/", payload(), format="json").status_code == 400


def test_audio_uses_existing_asr_and_preserves_original(ctx, monkeypatch, tmp_path):
    _, api = ctx
    from apps.capturas import pipeline

    monkeypatch.setattr(pipeline, "copiar_audio_para_asr", lambda _: tmp_path / "voice.wav")
    data = payload("OTRO")
    data.pop("texto")
    data["audio"] = SimpleUploadedFile("voice.wav", b"RIFF" + b"0" * 100, content_type="audio/wav")
    response = api.post("/api/v1/capturas/catalogo/", data, format="multipart")
    assert response.status_code == 202, response.data

    class ASR:
        def transcribe(self, path):
            return SimpleNamespace(
                text_original="nombre: Zócalo; descripción: alto tráfico",
                latency_ms=1,
                model_version="small-cpu-int8",
            )

    assert (
        procesar_intento(intento_id=response.data["intento_id"], servicio_asr=ASR()) == "FINALIZADO"
    )
    original = Captura.objects.get(pk=response.data["id"])
    assert original.texto_transcrito.startswith("nombre: Zócalo")


def test_encargado_identity_and_required_catalog_access(ctx):
    _, api = ctx
    identity = api.get("/api/v1/auth/me/")
    assert identity.data["capabilities"] == ["catalogo.crear_producto"]
    assert api.get("/api/v1/catalogo/productos/").status_code == 200
    assert api.get("/api/v1/catalogo/familias/").status_code == 200
    assert api.get("/api/v1/catalogo/opciones/?concepto=COLOR").status_code == 200
    assert api.get("/api/v1/proformas/").status_code == 403


def test_inactive_values_and_foreign_capture_are_not_available(ctx, django_user_model):
    _, api = ctx
    from apps.catalogo.models import ConceptoCatalogo, ValorCatalogo

    concept, _ = ConceptoCatalogo.objects.get_or_create(codigo="MARCA")
    ValorCatalogo.objects.create(concepto=concept, codigo="HOMEX", nombre="Homex", activo=False)
    data = {**payload(), "texto": "marca Homex; nombre silla de prueba"}
    response = api.post("/api/v1/capturas/catalogo/", data, format="json")
    assert response.status_code == 202
    assert procesar_intento(intento_id=response.data["intento_id"]) == "FINALIZADO"
    url = f"/api/v1/capturas/catalogo/{response.data['id']}/"
    assert "marca" not in api.get(url).data["propuesta"]["fields"]
    other = django_user_model.objects.create_user(username="otro-encargado")
    other.groups.add(Group.objects.get(name="ENCARGADO_TIENDA"))
    api.force_authenticate(other)
    assert api.get(url).status_code == 404


def test_partial_words_models_and_foreign_prices_stay_empty(ctx):
    _, api = ctx
    response = api.post(
        "/api/v1/capturas/catalogo/",
        {
            **payload(),
            "texto": "Nombres especiales. Modelo B quince. Precio unitario 100 dólares.",
        },
        format="json",
    )
    assert procesar_intento(intento_id=response.data["intento_id"]) == "FINALIZADO"
    result = api.get(f"/api/v1/capturas/catalogo/{response.data['id']}/").data["propuesta"]
    assert not {"nombre", "modelo", "precio_lista"} & result["fields"].keys()
    assert result["warnings"]


def test_secondary_color_contract_and_natural_specs(ctx):
    _, api = ctx
    from apps.catalogo.models import ConceptoCatalogo, ValorCatalogo

    concept, _ = ConceptoCatalogo.objects.get_or_create(
        codigo="COLOR", defaults={"descripcion": "Color"}
    )
    first = ValorCatalogo.objects.create(concepto=concept, codigo="NEGRO", nombre="Negro")
    second = ValorCatalogo.objects.create(concepto=concept, codigo="AZUL", nombre="Azul")
    response = api.post(
        "/api/v1/capturas/catalogo/",
        {
            **payload(),
            "texto": (
                "Silla ergonómica de malla. Color negro con azul. Modelo B15 con apoyo lumbar."
            ),
        },
        format="json",
    )
    assert procesar_intento(intento_id=response.data["intento_id"]) == "FINALIZADO"
    result = api.get(f"/api/v1/capturas/catalogo/{response.data['id']}/").data
    fields = result["propuesta"]["fields"]
    assert fields["color_primario"] == first.id
    assert fields["color_secundario"] == second.id
    assert fields["modelo"] == "B15"
    assert fields["especificaciones"]["material_respaldo"] == "malla"
    assert not Producto.objects.exists()


def test_rejected_backend_fields_do_not_keep_accepted_evidence(ctx):
    _, api = ctx
    response = api.post(
        "/api/v1/capturas/catalogo/",
        {**payload(), "texto": "nombre: Silla; precio unitario cien dólares"},
        format="json",
    )
    assert procesar_intento(intento_id=response.data["intento_id"]) == "FINALIZADO"
    proposal = api.get(f"/api/v1/capturas/catalogo/{response.data['id']}/").data["propuesta"]
    assert "precio_lista" not in proposal["fields"]
    assert all(
        e["decision"] != "ACCEPTED" for e in proposal["evidence"] if e["label"] == "precio_lista"
    )
