from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from apps.capturas.models import Captura, RevisionAsistida, TrabajoOutbox
from apps.capturas.pipeline import procesar_intento
from apps.proformas.models import DetalleProforma, Proforma
from tests.api.test_ap3_proformas_integrales import payload_integral
from tests.factories import vendedor

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def contexto(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="prf04"))
    api = APIClient()
    api.force_authenticate(actor)
    entrada = {
        "clave_idempotencia": str(uuid4()),
        "sesion_borrador": str(uuid4()),
        "moneda_codigo": "BOB",
        "texto": "tres escritorios, total 100 bolivianos",
    }
    return actor, api, entrada


def test_captura_sin_proforma_y_guardado_integral_atomico(contexto):
    actor, api, entrada = contexto
    respuesta = api.post("/api/v1/capturas/asistidas/", entrada, format="json")
    assert respuesta.status_code == 202, respuesta.data
    assert Proforma.objects.count() == DetalleProforma.objects.count() == 0
    assert TrabajoOutbox.objects.filter(intento_id=respuesta.data["intento_id"]).count() == 1
    assert procesar_intento(intento_id=respuesta.data["intento_id"]) == "FINALIZADO"
    url = f"/api/v1/capturas/asistidas/{respuesta.data['id']}/"
    revision = api.get(url)
    assert revision.status_code == 200
    assert revision.data["propuesta_configurador"]["comercial"]["precio_unitario"] is None
    assert Proforma.objects.count() == DetalleProforma.objects.count() == 0
    payload = payload_integral(clave=uuid4())
    payload["sesion_borrador"] = entrada["sesion_borrador"]
    payload["detalles"][0]["captura_asistida_id"] = respuesta.data["id"]
    guardado = api.post("/api/v1/proformas/integral/", payload, format="json")
    assert guardado.status_code == 201, guardado.data
    captura = Captura.objects.get(pk=respuesta.data["id"])
    assert captura.proforma_id == guardado.data["id"]
    assert captura.proforma_detalle_id == guardado.data["detalles"][0]["id"]
    assert RevisionAsistida.objects.count() == 1
    assert api.post("/api/v1/proformas/integral/", payload, format="json").status_code == 200
    assert RevisionAsistida.objects.count() == 1
    replay = api.post("/api/v1/capturas/asistidas/", entrada, format="json")
    assert replay.status_code == 202 and replay.data["reutilizada"] is True


@pytest.mark.parametrize(
    "campo,valor", [("texto", "otro texto"), ("sesion_borrador", None), ("moneda_codigo", "USD")]
)
def test_idempotencia_estricta(contexto, campo, valor):
    _, api, entrada = contexto
    assert api.post("/api/v1/capturas/asistidas/", entrada, format="json").status_code == 202
    entrada[campo] = valor or str(uuid4())
    assert api.post("/api/v1/capturas/asistidas/", entrada, format="json").status_code == 409
    assert Captura.objects.count() == 1


def test_rollback_sesion_incompatible(contexto):
    _, api, entrada = contexto
    respuesta = api.post("/api/v1/capturas/asistidas/", entrada, format="json")
    procesar_intento(intento_id=respuesta.data["intento_id"])
    payload = payload_integral(clave=uuid4())
    payload["sesion_borrador"] = str(uuid4())
    payload["detalles"][0]["captura_asistida_id"] = respuesta.data["id"]
    assert api.post("/api/v1/proformas/integral/", payload, format="json").status_code == 409
    assert Proforma.objects.count() == DetalleProforma.objects.count() == 0
    assert RevisionAsistida.objects.count() == 0


def test_ownership_y_ruta_historica(contexto, django_user_model):
    _, api, entrada = contexto
    respuesta = api.post("/api/v1/capturas/asistidas/", entrada, format="json")
    capture_id = respuesta.data["id"]
    assert api.get(f"/api/v1/capturas/{capture_id}/").status_code == 404
    assert (
        api.post(f"/api/v1/capturas/{capture_id}/confirmar/", {}, format="json").status_code == 404
    )
    api.force_authenticate(vendedor(django_user_model.objects.create_user(username="ajeno-prf04")))
    assert api.get(f"/api/v1/capturas/asistidas/{capture_id}/").status_code == 404


@pytest.mark.parametrize("extra", [{"proforma_detalle": 1}, {"inesperado": "x"}, {"audio": "x"}])
def test_rechaza_campos_incompatibles(contexto, extra):
    _, api, entrada = contexto
    assert (
        api.post("/api/v1/capturas/asistidas/", entrada | extra, format="json").status_code == 400
    )
    assert Captura.objects.count() == 0


def test_sin_propuesta_y_captura_pendiente_no_se_vinculan(contexto):
    _, api, entrada = contexto
    entrada["texto"] = "dos escritorios y tres veladores"
    respuesta = api.post("/api/v1/capturas/asistidas/", entrada, format="json")
    payload = payload_integral(clave=uuid4())
    payload["sesion_borrador"] = entrada["sesion_borrador"]
    payload["detalles"][0]["captura_asistida_id"] = respuesta.data["id"]
    assert api.post("/api/v1/proformas/integral/", payload, format="json").status_code == 400
    procesar_intento(intento_id=respuesta.data["intento_id"])
    detalle = api.get(f"/api/v1/capturas/asistidas/{respuesta.data['id']}/")
    assert detalle.data["resultado"] == "NO_PROPOSAL"
    assert detalle.data["propuesta_configurador"] is None
    assert api.post("/api/v1/proformas/integral/", payload, format="json").status_code == 400
    assert Proforma.objects.count() == DetalleProforma.objects.count() == 0


def test_reinterpretacion_conserva_evidencia_y_origen(contexto):
    _, api, entrada = contexto
    primera = api.post("/api/v1/capturas/asistidas/", entrada, format="json").data
    procesar_intento(intento_id=primera["intento_id"])
    entrada2 = entrada | {
        "clave_idempotencia": str(uuid4()),
        "texto": "un escritorio con tapa de 25 mm",
        "captura_origen": primera["id"],
    }
    segunda = api.post("/api/v1/capturas/asistidas/", entrada2, format="json")
    assert segunda.status_code == 202
    assert Captura.objects.get(pk=primera["id"]).texto_transcrito == entrada["texto"]
    assert Captura.objects.get(pk=segunda.data["id"]).captura_origen_id == primera["id"]


@pytest.mark.parametrize("estado", ["BORRADOR", "EN_REVISION", "APROBADA", "NO_CONCRETADA"])
def test_estado_existente_coincide_con_editor(contexto, estado):
    from apps.proformas.services import agregar_detalle, crear_proforma
    from tests.factories import cliente_persona, valor

    actor, api, entrada = contexto
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    detalle_previo = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
        nombre="Escritorio",
        cantidad="1.0000",
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        modo_calculo="PRECIO_UNITARIO",
        precio_unitario="100.00",
    )
    from apps.proformas.models import EspecificacionMueble

    EspecificacionMueble.objects.create(proforma_detalle=detalle_previo, datos_tecnicos={})
    proforma.estado = valor("ESTADO_PROFORMA", estado)
    proforma.save(update_fields=["estado"])
    entrada["proforma"] = proforma.id
    respuesta = api.post("/api/v1/capturas/asistidas/", entrada, format="json")
    assert respuesta.status_code == (202 if estado in {"BORRADOR", "EN_REVISION"} else 400)


def test_cadena_reinterpretaciones_conserva_original_y_vincula_ultima_evidencia(contexto):
    _, api, entrada = contexto
    primera = api.post("/api/v1/capturas/asistidas/", entrada, format="json")
    assert primera.status_code == 202
    assert procesar_intento(intento_id=primera.data["intento_id"]) == "FINALIZADO"

    textos = [
        "un escritorio con tapa de 25 mm",
        "un escritorio con tapa de 18 mm",
    ]
    origen = primera.data["id"]
    for texto in textos:
        siguiente = api.post(
            "/api/v1/capturas/asistidas/",
            entrada
            | {
                "clave_idempotencia": str(uuid4()),
                "texto": texto,
                "captura_origen": origen,
            },
            format="json",
        )
        assert siguiente.status_code == 202, siguiente.data
        assert procesar_intento(intento_id=siguiente.data["intento_id"]) == "FINALIZADO"
        revision = api.get(f"/api/v1/capturas/asistidas/{siguiente.data['id']}/")
        assert revision.status_code == 200
        assert revision.data["texto_transcrito_original"] == texto
        assert Captura.objects.get(pk=siguiente.data["id"]).captura_origen_id == origen
        origen = siguiente.data["id"]

    original = Captura.objects.get(pk=primera.data["id"])
    assert original.texto_transcrito == entrada["texto"]
    assert original.captura_origen_id is None
    assert Captura.objects.count() == 3

    payload = payload_integral(clave=uuid4())
    payload["sesion_borrador"] = entrada["sesion_borrador"]
    payload["detalles"][0]["captura_asistida_id"] = origen
    guardado = api.post("/api/v1/proformas/integral/", payload, format="json")
    assert guardado.status_code == 201, guardado.data
    evidencia = RevisionAsistida.objects.get()
    assert evidencia.captura_id == origen
    assert evidencia.detalle_id == guardado.data["detalles"][0]["id"]
    assert original.proforma_detalle_id is None
    assert Captura.objects.get(pk=origen).proforma_detalle_id == evidencia.detalle_id


def test_reinterpretar_no_admite_origen_de_otra_sesion(contexto):
    _, api, entrada = contexto
    primera = api.post("/api/v1/capturas/asistidas/", entrada, format="json")
    assert primera.status_code == 202
    otra = api.post(
        "/api/v1/capturas/asistidas/",
        entrada
        | {
            "clave_idempotencia": str(uuid4()),
            "sesion_borrador": str(uuid4()),
            "texto": "un escritorio con tapa de 18 mm",
            "captura_origen": primera.data["id"],
        },
        format="json",
    )
    assert otra.status_code == 404
    assert Captura.objects.count() == 1


def test_revision_semantica_e_intento_son_inmutables(contexto):
    from django.db import DatabaseError, transaction

    _, api, entrada = contexto
    respuesta = api.post("/api/v1/capturas/asistidas/", entrada, format="json").data
    procesar_intento(intento_id=respuesta["intento_id"])
    payload = payload_integral(clave=uuid4())
    payload["sesion_borrador"] = entrada["sesion_borrador"]
    payload["detalles"][0]["captura_asistida_id"] = respuesta["id"]
    assert api.post("/api/v1/proformas/integral/", payload, format="json").status_code == 201
    revision = RevisionAsistida.objects.get()
    with pytest.raises(DatabaseError), transaction.atomic():
        RevisionAsistida.objects.filter(pk=revision.pk).update(resultado_humano={})
    with pytest.raises(DatabaseError), transaction.atomic():
        revision.delete()
    with pytest.raises(DatabaseError), transaction.atomic():
        revision.intento.proyeccion_configurador = {}
        revision.intento.save(update_fields=["proyeccion_configurador"])


def test_lectura_administrativa_conserva_politica_historica(contexto, django_user_model):
    _, api, entrada = contexto
    captura = api.post("/api/v1/capturas/asistidas/", entrada, format="json").data
    admin = django_user_model.objects.create_user(username="admin-prf04", is_staff=True)
    api.force_authenticate(admin)
    respuesta = api.get(f"/api/v1/capturas/asistidas/{captura['id']}/")
    assert respuesta.status_code == 200
    assert respuesta.data["id"] == captura["id"]


def test_proyeccion_incompatible_conserva_evidencia_sin_escritura_comercial(contexto):
    from apps.capturas.models import IntentoCaptura

    _, api, entrada = contexto
    entrada["texto"] = "Un escritorio; " + "; ".join(["tapa de 25 mm"] * 41)
    captura = api.post("/api/v1/capturas/asistidas/", entrada, format="json").data
    assert procesar_intento(intento_id=captura["intento_id"]) == "ERROR"
    intento = IntentoCaptura.objects.get(pk=captura["intento_id"])
    assert intento.resultado_raw["text_original"] == entrada["texto"]
    assert intento.error_codigo == "PROYECCION_INCOMPATIBLE"
    respuesta = api.get(f"/api/v1/capturas/asistidas/{captura['id']}/")
    assert respuesta.data["resultado"] == "ERROR"
    assert respuesta.data["propuesta_configurador"] is None
    assert Proforma.objects.count() == DetalleProforma.objects.count() == 0


@pytest.mark.parametrize("material", ["melamine", "melamina"])
def test_v14_captura_conserva_original_y_proyecta_color_sin_conflicto(contexto, material):
    _, api, entrada = contexto
    entrada["texto"] = (
        f"Necesito un escritorio de {material} blanca, de un metro 20 de ancho, "
        "60 centímetros de profundidad y 75 centímetros de alto."
    )
    respuesta = api.post("/api/v1/capturas/asistidas/", entrada, format="json")
    assert respuesta.status_code == 202
    intento_id = respuesta.data["intento_id"]
    assert procesar_intento(intento_id=intento_id) == "FINALIZADO"
    revision = api.get(f"/api/v1/capturas/asistidas/{respuesta.data['id']}/")
    assert revision.status_code == 200
    assert revision.data["texto_transcrito_original"] == entrada["texto"]
    assert revision.data["resultado"] == "REQUIRES_REVIEW"
    p = revision.data["propuesta_configurador"]
    assert revision.data["version_proyeccion"] == "PRF04_2"
    generales = p["especificacion"]["datos_tecnicos"]["caracteristicas_generales"]
    assert generales["dimensiones"]["ancho"] == {"valor": "120", "unidad": "cm"}
    assert {a["nombre"]: a["valor"] for a in generales["atributos"]} == {
        "Material": material,
        "Color": "blanco",
    }
    assert not any(w["codigo"] in {"MISSING_UNIT", "CONFLICTING_VALUES"} for w in p["pendientes"])
    captura = Captura.objects.get(pk=respuesta.data["id"])
    intento = captura.intentocaptura_set.get(pk=intento_id)
    assert intento.resultado_raw["engine"]["rules_version"] == "prf04-rules-v14"
    assert intento.resultado_raw["text_original"] == entrada["texto"]
    assert Proforma.objects.count() == DetalleProforma.objects.count() == 0
    assert RevisionAsistida.objects.count() == 0
