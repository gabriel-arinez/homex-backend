from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from apps.proformas.services import agregar_detalle, crear_proforma
from tests.factories import cliente_persona, silla, valor, vendedor


def imagen():
    salida = BytesIO()
    Image.new("RGB", (640, 400), "red").save(salida, format="JPEG")
    return SimpleUploadedFile(
        "referencia.jpg",
        salida.getvalue(),
        content_type="image/jpeg",
    )


@pytest.mark.django_db(transaction=True)
def test_media_proforma_devuelve_403_a_vendedor_ajeno(django_user_model):
    propietario = vendedor(django_user_model.objects.create_user(username="media-propietario"))
    ajeno = vendedor(django_user_model.objects.create_user(username="media-ajeno"))

    producto = silla(propietario, sku="F077-MEDIA-403")
    proforma = crear_proforma(
        actor=propietario,
        cliente=cliente_persona(propietario),
    )
    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=propietario,
        tipo_item=valor("TIPO_ITEM", "SILLA"),
        producto_id=producto.id,
        nombre=producto.nombre,
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("50.00"),
    )

    cliente = APIClient()

    cliente.force_authenticate(propietario)
    respuesta = cliente.post(
        f"/api/v1/proformas/{proforma.id}/detalles/{detalle.id}/archivos/",
        {"archivo": imagen()},
        format="multipart",
    )
    assert respuesta.status_code == 201
    archivo_id = respuesta.data["id"]

    cliente.force_authenticate(ajeno)

    respuesta = cliente.get(f"/api/v1/proformas/{proforma.id}/detalles/{detalle.id}/archivos/")
    assert respuesta.status_code == 403

    respuesta = cliente.post(
        f"/api/v1/proformas/{proforma.id}/detalles/{detalle.id}/archivos/",
        {"archivo": imagen()},
        format="multipart",
    )
    assert respuesta.status_code == 403

    respuesta = cliente.delete(
        f"/api/v1/proformas/{proforma.id}/detalles/{detalle.id}/archivos/{archivo_id}/"
    )
    assert respuesta.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_producto_media_expone_dimensiones_y_acepta_ausencia(django_user_model):
    administrador = django_user_model.objects.create_user(
        username="media-producto-api-admin",
        is_staff=True,
    )
    producto = silla(
        administrador,
        sku="F077-MEDIA-DIMENSIONES",
    )

    cliente = APIClient()
    cliente.force_authenticate(administrador)

    respuesta = cliente.get(f"/api/v1/catalogo/productos/{producto.id}/")
    assert respuesta.status_code == 200
    assert respuesta.data["imagen_principal"] is None

    respuesta = cliente.post(
        f"/api/v1/catalogo/productos/{producto.id}/imagen-principal/",
        {"archivo": imagen()},
        format="multipart",
    )

    assert respuesta.status_code == 201

    media = respuesta.data["imagen_principal"]

    assert media["ancho"] == 640
    assert media["alto"] == 400
    assert set(media["variantes"]) == {"320", "640"}
    assert media["original"]
    assert all(media["variantes"].values())

    respuesta = cliente.get(f"/api/v1/catalogo/productos/{producto.id}/")
    assert respuesta.status_code == 200
    assert respuesta.data["imagen_principal"]["ancho"] == 640
    assert respuesta.data["imagen_principal"]["alto"] == 400


@pytest.mark.django_db(transaction=True)
def test_media_producto_restringe_mutaciones_a_administracion(django_user_model):
    administrador = django_user_model.objects.create_user(
        username="media-producto-admin-permisos",
        is_staff=True,
    )
    vendedor_ordinario = vendedor(
        django_user_model.objects.create_user(
            username="media-producto-vendedor-permisos",
        )
    )

    producto = silla(
        administrador,
        sku="F077-MEDIA-PERMISOS",
    )

    cliente = APIClient()
    cliente.force_authenticate(vendedor_ordinario)

    respuesta = cliente.post(
        f"/api/v1/catalogo/productos/{producto.id}/imagen-principal/",
        {"archivo": imagen()},
        format="multipart",
    )
    assert respuesta.status_code == 403

    respuesta = cliente.delete(f"/api/v1/catalogo/productos/{producto.id}/imagen-principal/")
    assert respuesta.status_code == 403

    cliente.force_authenticate(administrador)

    respuesta = cliente.post(
        f"/api/v1/catalogo/productos/{producto.id}/imagen-principal/",
        {"archivo": imagen()},
        format="multipart",
    )
    assert respuesta.status_code == 201
    assert "?" not in respuesta.data["imagen_principal"]["original"]

    respuesta = cliente.delete(f"/api/v1/catalogo/productos/{producto.id}/imagen-principal/")
    assert respuesta.status_code == 204


@pytest.mark.django_db(transaction=True)
def test_media_api_rechaza_tipo_y_tamano_invalidos_con_400(django_user_model):
    administrador = django_user_model.objects.create_user(
        username="media-producto-admin-invalidos",
        is_staff=True,
    )
    producto = silla(
        administrador,
        sku="F077-MEDIA-INVALIDOS",
    )

    cliente = APIClient()
    cliente.force_authenticate(administrador)

    svg = SimpleUploadedFile(
        "imagen.svg",
        b"<svg></svg>",
        content_type="image/svg+xml",
    )

    respuesta = cliente.post(
        f"/api/v1/catalogo/productos/{producto.id}/imagen-principal/",
        {"archivo": svg},
        format="multipart",
    )
    assert respuesta.status_code == 400

    base = imagen()
    contenido = base.read()
    contenido += b"x" * ((10 * 1024 * 1024 + 1) - len(contenido))

    demasiado_grande = SimpleUploadedFile(
        "grande.jpg",
        contenido,
        content_type="image/jpeg",
    )

    respuesta = cliente.post(
        f"/api/v1/catalogo/productos/{producto.id}/imagen-principal/",
        {"archivo": demasiado_grande},
        format="multipart",
    )
    assert respuesta.status_code == 400
