from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.exceptions import ValidationError

from apps.catalogo.services import reemplazar_imagen_principal
from apps.documentos.services import adjuntar_imagen
from apps.media.services import guardar_imagen
from apps.proformas.services import agregar_detalle, crear_proforma
from tests.factories import cliente_persona, silla, valor


def imagen(formato="JPEG", ancho=640, alto=400):
    salida = BytesIO()
    Image.new("RGB", (ancho, alto), "red").save(salida, format=formato)
    return SimpleUploadedFile("nombre-controlado.jpg", salida.getvalue(), content_type="image/jpeg")


@pytest.mark.django_db(transaction=True)
def test_imagen_producto_crea_key_y_variantes(django_user_model):
    actor = django_user_model.objects.create_superuser(username="media", password="x")
    producto = silla(actor, sku="MEDIA")
    reemplazar_imagen_principal(producto=producto, archivo=imagen(), actor=actor)
    producto.refresh_from_db()
    assert producto.imagen_principal.name.startswith("productos/")
    assert "http" not in producto.imagen_principal.name
    assert set(producto.imagen_principal_variantes) == {"320", "640"}


@pytest.mark.django_db(transaction=True)
def test_rechaza_audio_y_detalle_ajeno(django_user_model):
    actor = django_user_model.objects.create_user(username="media-vendedor")
    producto = silla(actor, sku="MEDIA-DETALLE")
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "SILLA"),
        producto=producto,
        nombre="Silla",
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=50,
    )
    otra = crear_proforma(actor=actor, cliente=cliente_persona(actor, sufijo="otra"))
    with pytest.raises(ValidationError):
        adjuntar_imagen(proforma_id=otra.id, detalle_id=detalle.id, archivo=imagen(), actor=actor)
    with pytest.raises(ValidationError):
        guardar_imagen(
            SimpleUploadedFile("audio.mp3", b"audio", content_type="audio/mpeg"),
            prefijo="proformas/",
        )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("formato", ["JPEG", "PNG", "WEBP"])
def test_normaliza_formatos_admitidos_y_no_amplia(formato):
    key, variantes, mime, _ = guardar_imagen(imagen(formato, 200, 100), prefijo="productos/")
    from django.core.files.storage import default_storage

    with default_storage.open(key, "rb") as archivo:
        salida = Image.open(archivo)
        assert salida.format == "WEBP"
        assert salida.size == (200, 100)
    assert variantes == {}
    assert mime == "image/webp"


@pytest.mark.django_db(transaction=True)
def test_adjunto_persiste_key_generada_y_rechaza_svg(django_user_model):
    actor = django_user_model.objects.create_user(username="media-adjunto")
    producto = silla(actor, sku="MEDIA-ADJUNTO")
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor, sufijo="adjunto"))
    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "SILLA"),
        producto=producto,
        nombre="Silla",
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=50,
    )
    adjunto = adjuntar_imagen(
        proforma_id=proforma.id, detalle_id=detalle.id, archivo=imagen(), actor=actor
    )
    assert adjunto.ruta_storage.startswith("proformas/")
    assert "nombre-controlado" not in adjunto.ruta_storage
    assert "http" not in adjunto.ruta_storage
    with pytest.raises(ValidationError):
        guardar_imagen(
            SimpleUploadedFile("imagen.svg", b"<svg></svg>", content_type="image/svg+xml"),
            prefijo="proformas/",
        )
