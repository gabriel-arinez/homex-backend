import pytest
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.proformas.validacion_tecnica import validar_datos_tecnicos
from tests.factories import vendedor


@pytest.mark.django_db
def test_catalogo_atributos_con_limites_busqueda_y_permiso(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="prf03-atributos"))
    api = APIClient()
    assert api.get("/api/v1/catalogo/atributos-mueble/").status_code == 401
    api.force_authenticate(actor)
    respuesta = api.get("/api/v1/catalogo/atributos-mueble/", {"search": "corredéra"})
    assert respuesta.status_code == 200
    assert respuesta.data["limites"] == {"max_conjuntos": 10, "max_componentes": 40}
    assert respuesta.data["atributos"][0]["codigo"] == "DESLIZAMIENTO_RIELES"


@pytest.mark.django_db(transaction=True)
def test_vendedor_crea_solo_tipo_mueble_y_duplicado_normalizado_es_409(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="prf03-tipo"))
    api = APIClient()
    api.force_authenticate(actor)
    creado = api.post(
        "/api/v1/catalogo/tipos-mueble/", {"nombre": "  Mesa   Reunión  "}, format="json"
    )
    assert creado.status_code == 201
    repetido = api.post("/api/v1/catalogo/tipos-mueble/", {"nombre": "mesa-reunion"}, format="json")
    assert repetido.status_code == 409
    assert repetido.data["codigo"] == "tipo_duplicado"
    assert repetido.data["existente"]["id"] == creado.data["id"]
    assert (
        api.post(
            "/api/v1/catalogo/tipos-mueble/",
            {"nombre": "Vitrina", "codigo": "FORZADO"},
            format="json",
        ).status_code
        == 400
    )


def ficha(conjuntos=1, componentes=1):
    grupos = [{"uid": f"g-{i}", "nombre": f"Grupo {i}"} for i in range(conjuntos)]
    piezas = [
        {
            "uid": f"p-{i}",
            "conjunto_uid": f"g-{i % conjuntos}" if conjuntos else None,
            "nombre": f"Pieza {i}",
            "cantidad_interna": 1,
            "atributos": [{"codigo": "MATERIAL", "nombre": "Material", "valor": "MDP"}],
        }
        for i in range(componentes)
    ]
    return {"conjuntos": grupos, "componentes": piezas, "extra_historico": {"se_conserva": True}}


def test_json_tecnico_aditivo_limites_vinculos_y_legado():
    assert validar_datos_tecnicos({"componentes": [{"nombre": "Legado", "desconocido": 1}]})
    assert validar_datos_tecnicos(ficha(10, 40))["extra_historico"] == {"se_conserva": True}
    with pytest.raises(Exception, match="Máximo 10"):
        validar_datos_tecnicos(ficha(11, 11))
    with pytest.raises(Exception, match="Máximo 40"):
        validar_datos_tecnicos(ficha(1, 41))
    datos = ficha(1, 1)
    datos["componentes"][0]["conjunto_uid"] = "ajeno"
    with pytest.raises(Exception, match="requiere al menos un componente"):
        validar_datos_tecnicos(datos)
    datos = ficha(1, 1)
    datos["componentes"][0]["atributos"].append(dict(datos["componentes"][0]["atributos"][0]))
    with pytest.raises(Exception, match="duplicado"):
        validar_datos_tecnicos(datos)


def test_json_tecnico_preserva_legado_sobre_limite_en_noop():
    legado = {"componentes": [{"nombre": f"Pieza {i}"} for i in range(41)]}
    assert validar_datos_tecnicos(legado, anteriores=legado) == legado
    cambiado = {**legado, "observacion_nueva": "cambio"}
    with pytest.raises(Exception, match="Máximo 40"):
        validar_datos_tecnicos(cambiado, anteriores=legado)


@pytest.mark.django_db(transaction=True)
@pytest.mark.concurrency
def test_creacion_concurrente_tipo_equivalente_no_duplica(django_user_model):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections

    from apps.catalogo.models import ValorCatalogo

    actor = vendedor(django_user_model.objects.create_user(username="prf03-tipo-concurrente"))
    barrera = Barrier(2)

    def crear(nombre):
        close_old_connections()
        api = APIClient()
        api.force_authenticate(actor)
        barrera.wait()
        respuesta = api.post("/api/v1/catalogo/tipos-mueble/", {"nombre": nombre}, format="json")
        close_old_connections()
        return respuesta.status_code, respuesta.data

    with ThreadPoolExecutor(max_workers=2) as executor:
        resultados = list(executor.map(crear, ["Mesa Directorio", " mesa-directorio "]))

    assert {estado for estado, _ in resultados} == {201, 409}
    assert (
        ValorCatalogo.objects.filter(
            concepto__codigo="TIPO_MUEBLE", codigo="MESA_DIRECTORIO"
        ).count()
        == 1
    )


def test_conjunto_uid_malformado_devuelve_validacion_en_vez_de_typeerror():
    for invalido in ([], {}, ["grupo"], {"uid": "grupo"}, 42):
        datos = ficha(1, 1)
        datos["componentes"][0]["conjunto_uid"] = invalido
        with pytest.raises(ValidationError, match="conjunto_uid"):
            validar_datos_tecnicos(datos)


@pytest.mark.django_db
def test_tipo_mueble_no_acepta_valor_de_otro_concepto(django_user_model):
    from apps.catalogo.models import ValorCatalogo
    from apps.proformas.api.serializers import EspecificacionMuebleSerializer

    otro = ValorCatalogo.objects.filter(concepto__codigo="TIPO_ITEM").first()
    assert otro is not None
    serializer = EspecificacionMuebleSerializer(data={"tipo_mueble": otro.pk, "datos_tecnicos": {}})
    assert not serializer.is_valid()
    assert "tipo_mueble" in serializer.errors


@pytest.mark.django_db(transaction=True)
def test_integral_preserva_legado_sin_cambiar_41_componentes(django_user_model):
    from decimal import Decimal

    from apps.proformas.api.serializers import DetalleIntegralSerializer
    from apps.proformas.models import EspecificacionMueble
    from apps.proformas.services import agregar_detalle, crear_proforma
    from tests.factories import valor

    actor = vendedor(django_user_model.objects.create_user(username="prf03-legado-integral"))
    proforma = crear_proforma(actor=actor)
    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
        nombre="Mueble antiguo",
        cantidad=Decimal("1"),
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("100.00"),
    )
    legado = {"componentes": [{"nombre": f"Parte {i}"} for i in range(41)]}
    EspecificacionMueble.objects.create(proforma_detalle=detalle, datos_tecnicos=legado)
    serializador = DetalleIntegralSerializer(
        data={
            "id": detalle.pk,
            "tipo_item": detalle.tipo_item_id,
            "nombre": detalle.nombre,
            "cantidad": "1",
            "unidad": detalle.unidad_id,
            "precio_unitario": "100.00",
            "descuento": "0.00",
            "especificacion": {"datos_tecnicos": legado, "observaciones": "Sin modificar"},
        },
        context={"proforma_actual": proforma},
    )
    assert serializador.is_valid(), serializador.errors
    assert serializador.validated_data["especificacion"]["datos_tecnicos"] == legado

def test_openapi_conflicto_tipo_mueble_documenta_el_existente():
    from drf_spectacular.generators import SchemaGenerator

    schema = SchemaGenerator().get_schema(public=True)
    endpoint = schema["paths"]["/api/v1/catalogo/tipos-mueble/"]["post"]
    assert endpoint["responses"]["201"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/TipoMuebleRespuesta"
    }
    assert endpoint["responses"]["409"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/TipoMuebleConflicto"
    }
    conflicto = schema["components"]["schemas"]["TipoMuebleConflicto"]
    assert set(conflicto["required"]) == {"codigo", "existente"}
    assert conflicto["properties"]["existente"]["$ref"] == (
        "#/components/schemas/TipoMuebleRespuesta"
    )
