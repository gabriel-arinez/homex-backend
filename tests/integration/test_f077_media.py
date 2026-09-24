from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.exceptions import ValidationError

from apps.catalogo.services import eliminar_imagen_principal, reemplazar_imagen_principal
from apps.documentos.services import adjuntar_imagen, eliminar_adjunto
from apps.media.services import guardar_imagen
from apps.proformas.services import agregar_detalle, crear_proforma
from tests.factories import cliente_persona, silla, valor, vendedor


def imagen(formato="JPEG", ancho=640, alto=400):
    salida = BytesIO()
    Image.new("RGB", (ancho, alto), "red").save(salida, format=formato)

    content_types = {
        "JPEG": "image/jpeg",
        "PNG": "image/png",
        "WEBP": "image/webp",
    }

    return SimpleUploadedFile(
        "nombre-controlado.jpg",
        salida.getvalue(),
        content_type=content_types[formato],
    )


@pytest.mark.django_db(transaction=True)
def test_imagen_producto_crea_key_y_variantes(django_user_model):
    actor = django_user_model.objects.create_superuser(username="media", password="x")
    producto = silla(actor, sku="MEDIA")
    reemplazar_imagen_principal(producto=producto, archivo=imagen(), actor=actor)
    producto.refresh_from_db()
    assert producto.imagen_principal.name.startswith("productos/")
    assert producto.imagen_principal_dimensiones == {
        "ancho": 640,
        "alto": 400,
    }
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
    key, variantes, dimensiones, mime, _ = guardar_imagen(
        imagen(formato, 200, 100),
        prefijo="productos/",
    )
    from django.core.files.storage import default_storage

    with default_storage.open(key, "rb") as archivo:
        salida = Image.open(archivo)
        assert salida.format == "WEBP"
        assert salida.size == (200, 100)
    assert variantes == {}
    assert dimensiones == {"ancho": 200, "alto": 100}
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


def test_rechaza_mime_audio_aunque_el_contenido_sea_imagen():
    salida = BytesIO()
    Image.new("RGB", (100, 100), "red").save(salida, format="JPEG")

    archivo = SimpleUploadedFile(
        "imagen.jpg",
        salida.getvalue(),
        content_type="audio/mpeg",
    )

    with pytest.raises(ValidationError):
        guardar_imagen(archivo, prefijo="proformas/")


def test_genera_variantes_320_640_1280_decodificables():
    from django.core.files.storage import default_storage

    key, variantes, dimensiones, mime, _ = guardar_imagen(
        imagen("JPEG", 1600, 900),
        prefijo="productos/",
    )

    assert mime == "image/webp"
    assert dimensiones == {"ancho": 1600, "alto": 900}
    assert set(variantes) == {"320", "640", "1280"}

    esperadas = {
        "320": (320, 180),
        "640": (640, 360),
        "1280": (1280, 720),
    }

    with default_storage.open(key, "rb") as archivo:
        original = Image.open(archivo)
        assert original.format == "WEBP"
        assert original.size == (1600, 900)

    for ancho, tamano in esperadas.items():
        with default_storage.open(variantes[ancho], "rb") as archivo:
            variante = Image.open(archivo)
            assert variante.format == "WEBP"
            assert variante.size == tamano


def test_normaliza_orientacion_exif_y_no_preserva_metadata():
    from django.core.files.storage import default_storage

    salida = BytesIO()
    origen = Image.new("RGB", (120, 60), "red")
    exif = origen.getexif()
    exif[274] = 6
    exif[270] = "metadata-no-necesaria"
    origen.save(salida, format="JPEG", exif=exif)

    archivo = SimpleUploadedFile(
        "orientada.jpg",
        salida.getvalue(),
        content_type="image/jpeg",
    )

    key, _, dimensiones, _, _ = guardar_imagen(
        archivo,
        prefijo="productos/",
    )

    assert dimensiones == {"ancho": 60, "alto": 120}

    with default_storage.open(key, "rb") as almacenada:
        imagen_salida = Image.open(almacenada)
        imagen_salida.load()

        assert imagen_salida.format == "WEBP"
        assert imagen_salida.size == (60, 120)
        assert imagen_salida.getexif().get(274) is None
        assert imagen_salida.getexif().get(270) is None


def test_rechaza_archivo_superior_a_10_mib():
    archivo = SimpleUploadedFile(
        "demasiado-grande.jpg",
        b"x" * (10 * 1024 * 1024 + 1),
        content_type="image/jpeg",
    )

    with pytest.raises(ValidationError) as exc:
        guardar_imagen(archivo, prefijo="productos/")

    assert "10 MiB" in str(exc.value)


def test_rechaza_contenido_falso_con_mime_de_imagen():
    archivo = SimpleUploadedFile(
        "falsa.jpg",
        b"esto no es realmente una imagen",
        content_type="image/jpeg",
    )

    with pytest.raises(ValidationError) as exc:
        guardar_imagen(archivo, prefijo="productos/")

    assert "no es una imagen válida" in str(exc.value)


@pytest.mark.django_db(transaction=True)
def test_reemplazo_y_eliminacion_producto_no_dejan_objetos_huerfanos(
    django_user_model,
):
    from django.core.files.storage import default_storage

    actor = django_user_model.objects.create_user(
        username="media-producto-admin",
        is_staff=True,
    )
    producto = silla(actor, sku="F077-CLEAN-PRODUCTO")

    reemplazar_imagen_principal(
        producto=producto,
        archivo=imagen("JPEG", 640, 400),
        actor=actor,
    )
    producto.refresh_from_db()

    claves_anteriores = [
        producto.imagen_principal.name,
        *producto.imagen_principal_variantes.values(),
    ]

    assert all(default_storage.exists(clave) for clave in claves_anteriores)

    reemplazar_imagen_principal(
        producto=producto,
        archivo=imagen("JPEG", 1600, 900),
        actor=actor,
    )
    producto.refresh_from_db()

    claves_nuevas = [
        producto.imagen_principal.name,
        *producto.imagen_principal_variantes.values(),
    ]

    assert all(not default_storage.exists(clave) for clave in claves_anteriores)
    assert all(default_storage.exists(clave) for clave in claves_nuevas)

    eliminar_imagen_principal(
        producto=producto,
        actor=actor,
    )
    producto.refresh_from_db()

    assert not producto.imagen_principal
    assert producto.imagen_principal_variantes == {}
    assert all(not default_storage.exists(clave) for clave in claves_nuevas)


@pytest.mark.django_db(transaction=True)
def test_eliminar_adjunto_borra_original_y_variantes(
    django_user_model,
):
    from django.core.files.storage import default_storage

    actor = django_user_model.objects.create_user(
        username="media-adjunto-vendedor",
    )
    vendedor(actor)

    producto = silla(actor, sku="F077-CLEAN-ADJUNTO")
    proforma = crear_proforma(
        actor=actor,
        cliente=cliente_persona(actor),
    )
    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "SILLA"),
        producto=producto,
        nombre=producto.nombre,
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=50,
    )

    adjunto = adjuntar_imagen(
        proforma_id=proforma.id,
        detalle_id=detalle.id,
        archivo=imagen("JPEG", 1600, 900),
        actor=actor,
    )

    parent = adjunto.ruta_storage.rsplit("/", 1)[0]
    claves = [
        adjunto.ruta_storage,
        f"{parent}/320.webp",
        f"{parent}/640.webp",
        f"{parent}/1280.webp",
    ]

    assert all(default_storage.exists(clave) for clave in claves)

    adjunto_id = adjunto.id

    eliminar_adjunto(
        proforma_id=proforma.id,
        detalle_id=detalle.id,
        archivo_id=adjunto_id,
        actor=actor,
    )

    from apps.documentos.models import ArchivoAdjunto

    assert not ArchivoAdjunto.objects.filter(pk=adjunto_id).exists()
    assert all(not default_storage.exists(clave) for clave in claves)


@pytest.mark.django_db(transaction=True)
def test_fallo_parcial_storage_limpia_nuevos_objetos_y_preserva_producto(
    django_user_model,
    monkeypatch,
):
    from django.core.files.storage import default_storage

    actor = django_user_model.objects.create_user(
        username="media-storage-failure-admin",
        is_staff=True,
    )
    producto = silla(actor, sku="F077-STORAGE-FAIL")

    reemplazar_imagen_principal(
        producto=producto,
        archivo=imagen("JPEG", 640, 400),
        actor=actor,
    )
    producto.refresh_from_db()

    original_anterior = producto.imagen_principal.name
    variantes_anteriores = dict(producto.imagen_principal_variantes)
    claves_anteriores = [
        original_anterior,
        *variantes_anteriores.values(),
    ]

    assert all(default_storage.exists(clave) for clave in claves_anteriores)

    save_real = default_storage.save
    intentos = [0]
    creados = []

    def save_con_fallo(name, content, max_length=None):
        intentos[0] += 1
        if intentos[0] == 2:
            raise OSError("storage indisponible")
        clave = save_real(name, content, max_length=max_length)
        creados.append(clave)
        return clave

    monkeypatch.setattr(default_storage, "save", save_con_fallo)

    with pytest.raises(OSError, match="storage indisponible"):
        reemplazar_imagen_principal(
            producto=producto,
            archivo=imagen("JPEG", 1600, 900),
            actor=actor,
        )

    producto.refresh_from_db()

    assert producto.imagen_principal.name == original_anterior
    assert producto.imagen_principal_variantes == variantes_anteriores

    assert all(default_storage.exists(clave) for clave in claves_anteriores)
    assert creados
    assert all(not default_storage.exists(clave) for clave in creados)
