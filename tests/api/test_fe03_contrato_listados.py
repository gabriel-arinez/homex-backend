import pytest
from rest_framework.test import APIClient

from apps.catalogo.models import Producto
from apps.clientes.models import Cliente
from tests.factories import silla, valor, vendedor


@pytest.mark.django_db
def test_clientes_listado_busca_filtra_pagina_y_conserva_aislamiento(django_user_model):
    propietario = vendedor(django_user_model.objects.create_user(username="fe03-clientes-owner"))
    ajeno = vendedor(django_user_model.objects.create_user(username="fe03-clientes-other"))
    tipo_persona = valor("TIPO_CLIENTE", "PERSONA")
    tipo_empresa = valor("TIPO_CLIENTE", "EMPRESA")

    Cliente.objects.create(
        tipo_cliente=tipo_persona,
        nombres="Ana",
        apellidos="López",
        celular="70000001",
        activo=True,
        created_by=propietario,
        updated_by=propietario,
    )
    empresa_propia = Cliente.objects.create(
        tipo_cliente=tipo_empresa,
        nombres="María",
        apellidos="Quispe",
        empresa="Empresa Norte",
        celular="70000002",
        activo=False,
        created_by=propietario,
        updated_by=propietario,
    )
    Cliente.objects.create(
        tipo_cliente=tipo_empresa,
        nombres="Julia",
        apellidos="Mamani",
        empresa="Empresa Ajena",
        celular="70000003",
        activo=False,
        created_by=ajeno,
        updated_by=ajeno,
    )

    cliente = APIClient()
    cliente.force_authenticate(propietario)

    respuesta = cliente.get(
        "/api/v1/clientes/",
        {
            "search": "empresa",
            "activo": "false",
            "tipo_cliente": tipo_empresa.id,
            "page_size": 1,
        },
    )

    assert respuesta.status_code == 200
    assert respuesta.data["count"] == 1
    assert respuesta.data["next"] is None
    assert respuesta.data["previous"] is None
    assert [item["id"] for item in respuesta.data["results"]] == [empresa_propia.id]


@pytest.mark.django_db
def test_clientes_paginacion_y_filtros_invalidos(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="fe03-clientes-page"))
    tipo = valor("TIPO_CLIENTE", "PERSONA")
    for indice in range(3):
        Cliente.objects.create(
            tipo_cliente=tipo,
            nombres=f"Cliente {indice}",
            apellidos="Prueba",
            activo=True,
            created_by=actor,
            updated_by=actor,
        )

    cliente = APIClient()
    cliente.force_authenticate(actor)

    respuesta = cliente.get("/api/v1/clientes/", {"page_size": 1})
    assert respuesta.status_code == 200
    assert respuesta.data["count"] == 3
    assert len(respuesta.data["results"]) == 1
    assert respuesta.data["next"] is not None

    assert cliente.get("/api/v1/clientes/", {"activo": "tal-vez"}).status_code == 400
    assert cliente.get("/api/v1/clientes/", {"tipo_cliente": 0}).status_code == 400


@pytest.mark.django_db
def test_productos_listado_busca_filtra_y_pagina(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="fe03-productos"))
    categoria_silla = valor("CATEGORIA_PRODUCTO", "SILLA")
    categoria_piso = valor("CATEGORIA_PRODUCTO", "PISO_FLOTANTE")
    unidad_pieza = valor("UNIDAD_MEDIDA", "PIEZA")

    alfa = silla(actor, sku="FE03-ALFA")
    beta = silla(actor, sku="FE03-BETA")
    beta.activo = False
    beta.save(update_fields=["activo"])
    Producto.objects.create(
        categoria=categoria_piso,
        sku="FE03-PISO",
        nombre="Piso Roble",
        precio_lista="120.00",
        stock=0,
        unidad_stock=unidad_pieza,
        activo=True,
        created_by=actor,
        updated_by=actor,
    )

    cliente = APIClient()
    cliente.force_authenticate(actor)

    respuesta = cliente.get(
        "/api/v1/catalogo/productos/",
        {
            "search": "alfa",
            "categoria": categoria_silla.id,
            "activo": "true",
            "page_size": 1,
        },
    )
    assert respuesta.status_code == 200
    assert respuesta.data["count"] == 1
    assert respuesta.data["results"][0]["id"] == alfa.id

    paginada = cliente.get(
        "/api/v1/catalogo/productos/",
        {"categoria": categoria_silla.id, "page_size": 1},
    )
    assert paginada.status_code == 200
    assert paginada.data["count"] == 2
    assert len(paginada.data["results"]) == 1
    assert paginada.data["next"] is not None

    assert cliente.get("/api/v1/catalogo/productos/", {"activo": "tal-vez"}).status_code == 400
    assert cliente.get("/api/v1/catalogo/productos/", {"categoria": 0}).status_code == 400
