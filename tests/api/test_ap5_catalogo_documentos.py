from decimal import Decimal
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.catalogo.models import FamiliaProducto, Producto, ProductoPiso, ProductoSilla
from apps.documentos.pdf import _cliente, renderizar_proforma_pdf
from apps.proformas.models import EspecificacionMueble
from apps.proformas.services import agregar_detalle, crear_proforma, enviar_proforma
from tests.factories import cliente_persona, valor, vendedor


def payload(categoria, unidad, sku, **extra):
    return {
        "categoria": valor("CATEGORIA_PRODUCTO", categoria).id,
        "familia": extra.pop("familia", None),
        "sku": sku,
        "nombre": f"Producto {sku}",
        "precio_lista": "100.00",
        "unidad_stock": valor("UNIDAD_MEDIDA", unidad).id,
        "activo": True,
        **extra,
    }


@pytest.mark.django_db(transaction=True)
def test_alta_unificada_silla_piso_otro_y_permiso(django_user_model):
    admin = django_user_model.objects.create_user(username="ap5-admin", is_staff=True)
    ordinario = vendedor(django_user_model.objects.create_user(username="ap5-vendedor"))
    familia = FamiliaProducto.objects.create(codigo="AP5-F", nombre="Familia AP5", activo=True)
    api = APIClient()
    api.force_authenticate(ordinario)
    assert (
        api.post(
            "/api/v1/catalogo/productos/", payload("OTRO", "BARRA", "AP5-Z"), format="json"
        ).status_code
        == 403
    )

    api.force_authenticate(admin)
    silla = api.post(
        "/api/v1/catalogo/productos/",
        payload(
            "SILLA",
            "PIEZA",
            "AP5-S",
            familia=familia.id,
            silla={"modelo": "B15", "especificaciones": {"respaldo": "malla"}},
        ),
        format="json",
    )
    assert silla.status_code == 201, silla.data
    assert ProductoSilla.objects.get(producto_id=silla.data["id"]).modelo == "B15"
    assert silla.data["categoria_info"]["codigo"] == "SILLA"
    assert silla.data["familia_info"]["codigo"] == "AP5-F"

    piso = api.post(
        "/api/v1/catalogo/productos/",
        payload(
            "PISO_FLOTANTE",
            "M2",
            "AP5-P",
            piso={"modelo": "Roble", "espesor_mm": "8.00", "m2_por_caja": "2.2000"},
        ),
        format="json",
    )
    assert piso.status_code == 201, piso.data
    assert ProductoPiso.objects.get(producto_id=piso.data["id"]).m2_por_caja == Decimal("2.2000")

    otro = api.post("/api/v1/catalogo/productos/", payload("OTRO", "BARRA", "AP5-Z"), format="json")
    assert otro.status_code == 201, otro.data
    assert Producto.objects.get(pk=otro.data["id"]).stock == 0


@pytest.mark.django_db(transaction=True)
def test_alta_producto_es_atomica_y_valida_clasificacion(django_user_model):
    admin = django_user_model.objects.create_user(username="ap5-atomico", is_staff=True)
    api = APIClient()
    api.force_authenticate(admin)
    invalido = api.post(
        "/api/v1/catalogo/productos/",
        payload("PISO_FLOTANTE", "PIEZA", "AP5-INVALIDO", piso={}),
        format="json",
    )
    assert invalido.status_code == 400
    assert not Producto.objects.filter(sku="AP5-INVALIDO").exists()
    with patch(
        "apps.catalogo.api.serializers.ProductoSilla.objects.get_or_create",
        side_effect=RuntimeError("falla ficha"),
    ):
        with pytest.raises(RuntimeError):
            api.post(
                "/api/v1/catalogo/productos/",
                payload("SILLA", "PIEZA", "AP5-ROLLBACK", silla={}),
                format="json",
            )
    assert not Producto.objects.filter(sku="AP5-ROLLBACK").exists()


@pytest.mark.django_db(transaction=True)
def test_promocion_vigente_se_expone_sin_aplicacion_duplicada(django_user_model):
    admin = django_user_model.objects.create_user(username="ap5-promo", is_staff=True)
    api = APIClient()
    api.force_authenticate(admin)
    respuesta = api.post(
        "/api/v1/catalogo/productos/",
        payload(
            "OTRO",
            "JUEGO",
            "AP5-PROMO",
            promocion={"precio_antes": "100.00", "precio_ahora": "80.00", "activo": True},
        ),
        format="json",
    )
    assert respuesta.status_code == 201, respuesta.data
    assert respuesta.data["precio_vigente"] == Decimal("80.00")
    assert respuesta.data["promocion"]["vigente"] is True


@pytest.mark.django_db(transaction=True)
def test_pdf_proforma_es_historico_multipagina_y_omite_condiciones_vacias(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap5-pdf"))
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    for indice in range(28):
        detalle = agregar_detalle(
            proforma_id=proforma.id,
            actor=actor,
            tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
            nombre=f"Mueble especial {indice}",
            descripcion="Descripción extensa " * 12,
            cantidad=1,
            unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
            precio_unitario=Decimal("100.00"),
            descuento=Decimal("5.00"),
        )
        EspecificacionMueble.objects.create(
            proforma_detalle=detalle,
            datos_tecnicos={
                "componentes": [
                    {"nombre": "cuerpo", "material": "melamina", "detalle": "muy largo " * 8}
                ]
            },
        )
    enviar_proforma(proforma_id=proforma.id, actor=actor)
    proforma.refresh_from_db()
    nombre_historico = proforma.cliente_nombre_snapshot
    proforma.cliente.nombres = "Nombre cambiado posteriormente"
    proforma.cliente.save(update_fields=["nombres"])
    assert _cliente(proforma)[0] == nombre_historico
    contenido = renderizar_proforma_pdf(proforma.id)
    assert contenido.startswith(b"%PDF")
    assert contenido.count(b"/Type /Page") >= 2
    api = APIClient()
    api.force_authenticate(actor)
    respuesta = api.get(f"/api/v1/proformas/{proforma.id}/documento-pdf/")
    assert respuesta.status_code == 200
    assert respuesta["Content-Type"] == "application/pdf"
    assert respuesta["Content-Disposition"].endswith('.pdf"')
    ajeno = vendedor(django_user_model.objects.create_user(username="ap5-pdf-ajeno"))
    api.force_authenticate(ajeno)
    assert api.get(f"/api/v1/proformas/{proforma.id}/documento-pdf/").status_code == 404
