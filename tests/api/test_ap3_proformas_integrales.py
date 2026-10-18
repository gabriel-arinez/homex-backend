from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from apps.clientes.models import Cliente
from apps.proformas.models import DetalleProforma, EspecificacionMueble, Proforma
from apps.proformas.services import ErrorComercial, agregar_detalle, crear_proforma
from tests.factories import valor, vendedor


def payload_integral(*, clave, emitir=False, descuento="0.00"):
    return {
        "clave_idempotencia": str(clave),
        "emitir": emitir,
        "cliente_nuevo": {
            "tipo_cliente": valor("TIPO_CLIENTE", "PERSONA").id,
            "nombres": "Elena",
            "apellidos": "Mendoza",
            "celular": "70000001",
        },
        "titulo": "Oficina AP3",
        "moneda_codigo": "BOB",
        "plazo_entrega": "20 días",
        "validez_oferta": 15,
        "porcentaje_adelanto": "50.00",
        "detalles": [
            {
                "tipo_item": valor("TIPO_ITEM", "MUEBLE_MEDIDA").id,
                "producto": None,
                "familia_producto": None,
                "nombre": "Escritorio ejecutivo",
                "descripcion": "Fabricación a pedido",
                "cantidad": "1.0000",
                "unidad": valor("UNIDAD_MEDIDA", "PIEZA").id,
                "modo_calculo": "PRECIO_UNITARIO",
                "precio_unitario": "2500.00",
                "importe_negociado": None,
                "descuento": descuento,
                "especificacion": {
                    "tipo_mueble": valor("TIPO_MUEBLE", "MESA_REUNION").id,
                    "datos_tecnicos": {
                        "componentes": [
                            {
                                "nombre": "Mesón",
                                "material": "Melamina",
                                "atributo_abierto": {"canto": "2 mm"},
                            }
                        ],
                        "advertencias": ["Color a elección"],
                    },
                    "observaciones": "Confirmar color antes de producir",
                },
            }
        ],
    }


@pytest.mark.django_db(transaction=True)
def test_editor_no_persiste_hasta_guardado_integral_y_replay_es_idempotente(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap3-integral"))
    api = APIClient()
    api.force_authenticate(actor)
    clave = uuid4()
    payload = payload_integral(clave=clave)

    assert Proforma.objects.count() == 0
    assert Cliente.objects.count() == 0

    primera = api.post("/api/v1/proformas/integral/", payload, format="json")
    assert primera.status_code == 201
    assert primera.data["estado_info"]["codigo"] == "BORRADOR"
    assert primera.data["numero"] > 0
    assert primera.data["detalles"][0]["especificacion"]["datos_tecnicos"]["componentes"][0][
        "atributo_abierto"
    ] == {"canto": "2 mm"}

    repetida = api.post("/api/v1/proformas/integral/", payload, format="json")
    assert repetida.status_code == 200
    assert repetida.data["id"] == primera.data["id"]
    assert Proforma.objects.count() == 1
    assert Cliente.objects.count() == 1

    payload["titulo"] = "Operación diferente"
    conflicto = api.post("/api/v1/proformas/integral/", payload, format="json")
    assert conflicto.status_code == 409


@pytest.mark.django_db(transaction=True)
def test_emision_integral_es_atomica_y_fallo_no_deja_cliente_ni_proforma(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap3-rollback"))
    api = APIClient()
    api.force_authenticate(actor)

    invalida = api.post(
        "/api/v1/proformas/integral/",
        payload_integral(clave=uuid4(), emitir=True, descuento="3000.00"),
        format="json",
    )
    assert invalida.status_code == 400
    assert Proforma.objects.count() == 0
    assert Cliente.objects.count() == 0

    valida = api.post(
        "/api/v1/proformas/integral/",
        payload_integral(clave=uuid4(), emitir=True),
        format="json",
    )
    assert valida.status_code == 201
    assert valida.data["estado_info"]["codigo"] == "EN_REVISION"
    proforma = Proforma.objects.get(pk=valida.data["id"])
    assert proforma.total == 2500
    assert EspecificacionMueble.objects.filter(proforma_detalle__proforma=proforma).exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("precio", [None, "0.00", "-1.00"])
def test_linea_nueva_exige_precio_positivo_sin_persistencia_parcial(django_user_model, precio):
    actor = vendedor(django_user_model.objects.create_user(username=f"prf01-precio-{precio}"))
    api = APIClient()
    api.force_authenticate(actor)
    datos = payload_integral(clave=uuid4())
    if precio is None:
        datos["detalles"][0].pop("precio_unitario")
    else:
        datos["detalles"][0]["precio_unitario"] = precio

    respuesta = api.post("/api/v1/proformas/integral/", datos, format="json")

    assert respuesta.status_code == 400
    assert "precio_unitario" in str(respuesta.data)
    assert Proforma.objects.count() == 0
    assert Cliente.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_servicio_tambien_rechaza_precio_cero(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="prf01-servicio-precio"))
    proforma = crear_proforma(actor=actor)

    with pytest.raises(ErrorComercial, match="precio unitario mayor que cero"):
        agregar_detalle(
            proforma_id=proforma.id,
            actor=actor,
            tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
            nombre="Línea inválida",
            cantidad="1.0000",
            unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
            modo_calculo="PRECIO_UNITARIO",
            precio_unitario="0.00",
            descuento="0.00",
        )

    assert not DetalleProforma.objects.filter(proforma=proforma).exists()


@pytest.mark.django_db(transaction=True)
def test_put_integral_preserva_precio_omitido_y_valida_descuento(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="prf01-put-parcial"))
    api = APIClient()
    api.force_authenticate(actor)
    creada = api.post(
        "/api/v1/proformas/integral/",
        payload_integral(clave=uuid4()),
        format="json",
    )
    assert creada.status_code == 201
    linea_id = creada.data["detalles"][0]["id"]

    modificada = payload_integral(clave=uuid4())
    modificada["cliente_nuevo"] = None
    modificada["cliente"] = creada.data["cliente"]
    modificada["revision_esperada"] = creada.data["revision"]
    modificada["detalles"][0]["id"] = linea_id
    modificada["detalles"][0]["cantidad"] = "2.0000"
    modificada["detalles"][0].pop("precio_unitario")
    modificada["detalles"][0].pop("modo_calculo")

    respuesta = api.put(
        f"/api/v1/proformas/{creada.data['id']}/integral/",
        modificada,
        format="json",
    )
    assert respuesta.status_code == 200, respuesta.data
    assert respuesta.data["detalles"][0]["id"] == linea_id
    assert respuesta.data["detalles"][0]["precio_unitario"] == "2500.00"
    assert respuesta.data["total"] == "5000.00"

    modificada["revision_esperada"] = respuesta.data["revision"]
    modificada["detalles"][0]["descuento"] = "6000.00"
    rechazada = api.put(
        f"/api/v1/proformas/{creada.data['id']}/integral/",
        modificada,
        format="json",
    )
    assert rechazada.status_code == 400
    assert "descuento" in str(rechazada.data)
    assert DetalleProforma.objects.get(pk=linea_id).cantidad == 2


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("precio", ["incorrecto", "NaN", "Infinity", None])
def test_servicio_no_propaga_excepciones_por_precio_invalido(django_user_model, precio):
    actor = vendedor(django_user_model.objects.create_user(username=f"prf01-valor-{precio}"))
    proforma = crear_proforma(actor=actor)
    with pytest.raises(ErrorComercial, match="precio unitario mayor que cero"):
        agregar_detalle(
            proforma_id=proforma.id,
            actor=actor,
            tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
            nombre="Línea sin precio utilizable",
            cantidad="1.0000",
            unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
            modo_calculo="PRECIO_UNITARIO",
            precio_unitario=precio,
            descuento="0.00",
        )
    assert not DetalleProforma.objects.filter(proforma=proforma).exists()


@pytest.mark.django_db(transaction=True)
def test_sincronizacion_integral_conserva_ids_y_aisla_vendedores(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap3-owner"))
    ajeno = vendedor(django_user_model.objects.create_user(username="ap3-other"))
    api = APIClient()
    api.force_authenticate(actor)
    creada = api.post(
        "/api/v1/proformas/integral/",
        payload_integral(clave=uuid4()),
        format="json",
    )
    assert creada.status_code == 201
    linea_id = creada.data["detalles"][0]["id"]

    cuerpo = payload_integral(clave=uuid4())
    cuerpo["cliente_nuevo"] = None
    cuerpo["cliente"] = creada.data["cliente"]
    cuerpo["detalles"][0]["id"] = linea_id
    cuerpo["detalles"][0]["cantidad"] = "2.0000"
    cuerpo["revision_esperada"] = creada.data["revision"]
    actualizada = api.put(f"/api/v1/proformas/{creada.data['id']}/integral/", cuerpo, format="json")
    assert actualizada.status_code == 200
    assert actualizada.data["detalles"][0]["id"] == linea_id
    assert actualizada.data["total"] == "5000.00"

    api.force_authenticate(ajeno)
    respuesta_ajena = api.put(
        f"/api/v1/proformas/{creada.data['id']}/integral/", cuerpo, format="json"
    )
    assert respuesta_ajena.status_code == 404
