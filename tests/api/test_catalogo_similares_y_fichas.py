from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.catalogo.models import Producto, ProductoPiso, ProductoSilla
from tests.factories import silla, valor, vendedor


@pytest.mark.django_db
def test_fichas_silla_y_piso_exponen_nombres_legibles_y_creador(django_user_model):
    actor = vendedor(
        django_user_model.objects.create_user(
            username="cat-nombres",
            first_name="Lucía",
            last_name="Gómez",
        )
    )
    marca = valor("MARCA", "HOMEX_PRO")
    color1 = valor("COLOR", "NEGRO")
    color2 = valor("COLOR", "CROMO")
    tipo_piso = valor("TIPO_PISO", "LAMINADO")
    material = valor("MATERIAL_PISO", "HDF")
    diseno = valor("DISENO_PISO", "MADERA")
    acabado = valor("ACABADO_PISO", "MATE")

    prod_silla = silla(actor, sku="SIL-NOM-01")
    ProductoSilla.objects.update_or_create(
        producto=prod_silla,
        defaults={
            "marca": marca,
            "modelo": "Ergopro",
            "color_primario": color1,
            "color_secundario": color2,
            "created_by": actor,
            "updated_by": actor,
        },
    )

    prod_piso = Producto.objects.create(
        categoria=valor("CATEGORIA_PRODUCTO", "PISO_FLOTANTE"),
        sku="PIS-NOM-01",
        nombre="Piso Roble Alemán",
        precio_lista=Decimal("180.00"),
        unidad_stock=valor("UNIDAD_MEDIDA", "M2"),
        created_by=actor,
        updated_by=actor,
    )
    ProductoPiso.objects.create(
        producto=prod_piso,
        marca=marca,
        modelo="Roble 8mm",
        tipo=tipo_piso,
        material=material,
        diseno=diseno,
        acabado=acabado,
        espesor_mm=Decimal("8.00"),
        created_by=actor,
        updated_by=actor,
    )

    api = APIClient()
    api.force_authenticate(actor)

    res_silla = api.get(f"/api/v1/catalogo/productos/{prod_silla.id}/")
    assert res_silla.status_code == 200
    assert res_silla.data["creado_por_resumen"]["display_name"] == "Lucía Gómez"
    assert res_silla.data["silla"]["marca_nombre"] == marca.nombre
    assert res_silla.data["silla"]["color_primario_nombre"] == color1.nombre
    assert res_silla.data["silla"]["color_secundario_nombre"] == color2.nombre

    res_piso = api.get(f"/api/v1/catalogo/productos/{prod_piso.id}/")
    assert res_piso.status_code == 200
    assert res_piso.data["piso"]["marca_nombre"] == marca.nombre
    assert res_piso.data["piso"]["tipo_nombre"] == tipo_piso.nombre
    assert res_piso.data["piso"]["material_nombre"] == material.nombre
    assert res_piso.data["piso"]["diseno_nombre"] == diseno.nombre
    assert res_piso.data["piso"]["acabado_nombre"] == acabado.nombre


@pytest.mark.django_db
def test_verificar_similares_detecta_sku_duplicado_nombre_y_atributos(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="cat-similares"))
    marca = valor("MARCA", "HOMEX_SIM")
    color = valor("COLOR", "GRIS")
    existente = silla(actor, sku="SIL-EXACT-99", nombre="Silla Ejecutiva Mesh")
    ProductoSilla.objects.update_or_create(
        producto=existente,
        defaults={
            "marca": marca,
            "modelo": "NX-500",
            "color_primario": color,
            "created_by": actor,
            "updated_by": actor,
        },
    )

    api = APIClient()
    api.force_authenticate(actor)

    # 1. Detecta SKU duplicado (case-insensitive)
    r_sku = api.get(
        "/api/v1/catalogo/productos/verificar-similares/",
        {"sku": "sil-exact-99", "nombre": "Silla Ejecutiva Mesh"},
    )
    assert r_sku.status_code == 200
    assert r_sku.data["sku_duplicado"]["id"] == existente.id
    assert r_sku.data["sku_duplicado"]["coincidencia"] == "SKU_EXACTO"

    # 2. Excluye el mismo producto al editar
    r_edit = api.get(
        "/api/v1/catalogo/productos/verificar-similares/",
        {"exclude_id": existente.id, "sku": "SIL-EXACT-99", "nombre": "Silla Ejecutiva Mesh"},
    )
    assert r_edit.status_code == 200
    assert r_edit.data["sku_duplicado"] is None
    assert r_edit.data["similares"] == []

    # 3. Detecta nombre exacto y atributos iguales con otro SKU
    r_nombre = api.get(
        "/api/v1/catalogo/productos/verificar-similares/",
        {"sku": "SIL-NUEVO-01", "nombre": "  silla ejecutiva   mesh "},
    )
    assert r_nombre.status_code == 200
    assert r_nombre.data["sku_duplicado"] is None
    assert r_nombre.data["similares"][0]["id"] == existente.id
    assert r_nombre.data["similares"][0]["coincidencia"] == "NOMBRE_EXACTO"

    r_attrs = api.get(
        "/api/v1/catalogo/productos/verificar-similares/",
        {
            "sku": "SIL-NUEVO-02",
            "nombre": "Otro modelo distinto",
            "categoria": existente.categoria_id,
            "marca": marca.id,
            "modelo": "nx-500",
        },
    )
    assert r_attrs.status_code == 200
    assert r_attrs.data["similares"][0]["id"] == existente.id
    assert r_attrs.data["similares"][0]["coincidencia"] == "ATRIBUTOS_IGUALES"
