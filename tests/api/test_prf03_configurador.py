import pytest
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
            concepto__codigo="TIPO_MUEBLE", nombre="Mesa Directorio"
        ).count()
        == 1
    )
