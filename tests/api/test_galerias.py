from datetime import timedelta
from io import BytesIO
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from apps.catalogo.models import ImagenProducto
from apps.documentos.models import ArchivoAdjunto, GaleriaBorrador
from apps.media.storage import privado
from tests.api.test_ap3_proformas_integrales import payload_integral
from tests.factories import silla, vendedor

pytestmark = pytest.mark.django_db(transaction=True)


def foto(color="red", formato="PNG"):
    out = BytesIO()
    Image.new("RGB", (40, 30), color).save(out, format=formato)
    return SimpleUploadedFile(
        f"{color}.{formato.lower()}",
        out.getvalue(),
        content_type=f"image/{'jpeg' if formato == 'JPEG' else formato.lower()}",
    )


@pytest.fixture
def ctx(django_user_model, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    user = vendedor(django_user_model.objects.create_user(username="galeria-seller"))
    client = APIClient()
    client.force_authenticate(user)
    return user, client


def nueva(client, sesion=None, **kw):
    sesion = sesion or str(uuid4())
    r = client.post("/api/v1/galerias/", {"sesion": sesion, **kw}, format="json")
    assert r.status_code in (200, 201), r.data
    return sesion, r.data["id"], f"/api/v1/galerias/{r.data['id']}/imagenes/"


def subir(client, path, color="red"):
    r = client.post(path, {"archivo": foto(color)}, format="multipart")
    assert r.status_code == 200, r.data
    return r.data["imagenes"]


def test_catalogo_portada_independiente_orden_eliminacion_y_compatibilidad(ctx):
    user, api = ctx
    p = silla(user, sku="GALLERY")
    path = f"/api/v1/catalogo/productos/{p.pk}/imagenes/"
    first = subir(api, path)[0]["id"]
    second = subir(api, path, "blue")[1]["id"]
    assert api.patch(path, {"principal": second}, format="json").status_code == 200
    r = api.patch(path, {"orden": [second, first]}, format="json")
    assert [i["id"] for i in r.data["imagenes"]] == [second, first]
    assert r.data["imagenes"][0]["principal"]
    p.refresh_from_db()
    assert p.imagen_principal.name == ImagenProducto.objects.get(pk=second).ruta_storage
    r = api.patch(path, {"eliminar": second}, format="json")
    assert r.data["imagenes"][0]["id"] == first
    assert r.data["imagenes"][0]["principal"]
    assert api.patch(path, {"eliminar": first}, format="json").data["imagenes"] == []
    assert api.get(f"/api/v1/catalogo/productos/{p.pk}/").data["imagen_principal"] is None


def test_limites_duplicados_formatos_y_orden_manipulado(ctx, settings):
    user, api = ctx
    p = silla(user, sku="LIMIT")
    path = f"/api/v1/catalogo/productos/{p.pk}/imagenes/"
    subir(api, path)
    assert api.post(path, {"archivo": foto()}, format="multipart").status_code == 400
    assert (
        api.post(
            path,
            {"archivo": SimpleUploadedFile("x.svg", b"<svg/>", content_type="image/svg+xml")},
            format="multipart",
        ).status_code
        == 400
    )
    assert api.patch(path, {"orden": [[1]]}, format="json").status_code == 400
    assert api.patch(path, {"principal": 999999}, format="json").status_code == 400
    settings.HOMEX_GALLERY_MAX_IMAGES = 1
    assert api.post(path, {"archivo": foto("blue")}, format="multipart").status_code == 400
    assert ImagenProducto.objects.filter(producto=p).count() == 1


def test_borrador_vinculacion_integral_idempotencia_y_privacidad(ctx, django_user_model):
    user, api = ctx
    sesion, gallery, path = nueva(api)
    image = subir(api, path)[0]
    assert image["url"].startswith("/api/v1/imagenes-privadas/")
    obj = ArchivoAdjunto.objects.get(pk=image["id"])
    assert privado().exists(obj.ruta_storage)
    assert obj.proforma_detalle_id is None
    response = api.get(image["url"])
    assert response.status_code == 200
    assert response["Cache-Control"] == "private, no-store"
    response.close()
    other = vendedor(django_user_model.objects.create_user(username="other-gallery"))
    api.force_authenticate(other)
    assert api.get(path).status_code == 404
    assert api.get(image["url"]).status_code == 404
    api.force_authenticate(user)
    data = payload_integral(clave=str(uuid4()))
    data["sesion_borrador"] = sesion
    data["detalles"][0]["galeria_id"] = gallery
    result = api.post("/api/v1/proformas/integral/", data, format="json")
    assert result.status_code == 201, result.data
    obj.refresh_from_db()
    assert obj.proforma_detalle_id == result.data["detalles"][0]["id"]
    replay = api.post("/api/v1/proformas/integral/", data, format="json")
    assert replay.status_code == 200
    assert replay.data["id"] == result.data["id"]
    assert result.data["detalles"][0]["galeria_id"] == gallery


def test_borrador_sesion_ajena_hace_rollback_total(ctx):
    _, api = ctx
    _, gallery, path = nueva(api)
    image = subir(api, path)[0]
    data = payload_integral(clave=str(uuid4()))
    data["sesion_borrador"] = str(uuid4())
    data["detalles"][0]["galeria_id"] = gallery
    result = api.post("/api/v1/proformas/integral/", data, format="json")
    assert result.status_code == 400, result.data
    assert ArchivoAdjunto.objects.get(pk=image["id"]).proforma_detalle_id is None
    assert GaleriaBorrador.objects.get(pk=gallery).detalle_id is None


def test_duplicacion_independiente_limpieza_y_eliminacion_de_linea(ctx):
    _, api = ctx
    sesion, gallery, path = nueva(api)
    first = subir(api, path)[0]
    clave = str(uuid4())
    _, copy, clonepath = nueva(api, sesion, origen=gallery, id=clave)
    _, replay, _ = nueva(api, sesion, origen=gallery, id=clave)
    assert copy == replay
    copia = api.get(clonepath).data["imagenes"][0]
    a, b = ArchivoAdjunto.objects.get(pk=first["id"]), ArchivoAdjunto.objects.get(pk=copia["id"])
    assert a.ruta_storage != b.ruta_storage
    assert api.patch(clonepath, {"eliminar": b.pk}, format="json").status_code == 200
    assert privado().exists(a.ruta_storage)
    data = payload_integral(clave=str(uuid4()))
    data["sesion_borrador"] = sesion
    data["detalles"][0]["galeria_id"] = gallery
    result = api.post("/api/v1/proformas/integral/", data, format="json")
    assert result.status_code == 201, result.data
    detalle = result.data["detalles"][0]["id"]
    assert api.delete(f"/api/v1/proformas-detalle/{detalle}/").status_code == 204
    assert not ArchivoAdjunto.objects.filter(pk=a.pk).exists()
    assert not privado().exists(a.ruta_storage)
    GaleriaBorrador.objects.filter(pk=copy).update(actualizado=timezone.now() - timedelta(days=31))
    call_command("limpiar_galerias")
    assert not GaleriaBorrador.objects.filter(pk=copy).exists()


def test_permisos_vendedor_propietario_admin_y_taller(ctx, django_user_model):
    user, api = ctx
    from django.contrib.auth.models import Group

    p = silla(user, sku="OWNER")
    path = f"/api/v1/catalogo/productos/{p.pk}/imagenes/"
    subir(api, path)
    other = vendedor(django_user_model.objects.create_user(username="gallery-other"))
    api.force_authenticate(other)
    assert api.get(path).status_code == 200
    assert api.post(path, {"archivo": foto("blue")}, format="multipart").status_code == 403
    admin = django_user_model.objects.create_user(username="gallery-admin", is_staff=True)
    api.force_authenticate(admin)
    subir(api, path, "blue")
    jefe = django_user_model.objects.create_user(username="gallery-jefe")
    jefe.groups.add(Group.objects.get_or_create(name="JEFE_TALLER")[0])
    api.force_authenticate(jefe)
    assert api.post("/api/v1/galerias/", {"sesion": str(uuid4())}, format="json").status_code == 403
    assert api.post(path, {"archivo": foto("green")}, format="multipart").status_code == 403


@pytest.mark.concurrency
def test_cargas_concurrentes_respetan_limite(ctx, settings):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections

    settings.HOMEX_GALLERY_MAX_IMAGES = 1
    user, _ = ctx
    p = silla(user, sku="CONCURRENT-GALLERY")
    barrier = Barrier(2)

    def cargar(color):
        close_old_connections()
        try:
            client = APIClient()
            client.force_authenticate(user)
            barrier.wait(timeout=10)
            return client.post(
                f"/api/v1/catalogo/productos/{p.pk}/imagenes/",
                {"archivo": foto(color)},
                format="multipart",
            ).status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = list(pool.map(cargar, ["red", "blue"]))
    assert sorted(resultados) == [200, 400]
    assert p.imagenes.count() == 1


def test_fallo_de_persistencia_limpia_objetos_nuevos(ctx, monkeypatch):
    user, api = ctx
    p = silla(user, sku="FAIL-GALLERY")
    from django.core.files.storage import default_storage

    real = default_storage.save
    saved = []

    def store(*args, **kwargs):
        key = real(*args, **kwargs)
        saved.append(key)
        return key

    def fail(*args, **kwargs):
        raise RuntimeError("Fallo deliberado de persistencia")

    monkeypatch.setattr(default_storage, "save", store)
    monkeypatch.setattr(ImagenProducto.objects, "create", fail)
    with pytest.raises(RuntimeError, match="Fallo deliberado"):
        api.post(
            f"/api/v1/catalogo/productos/{p.pk}/imagenes/", {"archivo": foto()}, format="multipart"
        )
    assert saved
    assert all(not default_storage.exists(key) for key in saved)
    assert not p.imagenes.exists()


def test_taller_consulta_referencias_solo_con_orden_de_trabajo(ctx, django_user_model):
    from django.contrib.auth.models import Group

    from apps.pedidos.services import aprobar_proforma

    user, api = ctx
    sesion, gallery, path = nueva(api)
    image = subir(api, path)[0]
    data = payload_integral(clave=str(uuid4()), emitir=True)
    data["sesion_borrador"] = sesion
    data["detalles"][0]["galeria_id"] = gallery
    result = api.post("/api/v1/proformas/integral/", data, format="json")
    assert result.status_code == 201, result.data
    detalle = result.data["detalles"][0]["id"]
    jefe = django_user_model.objects.create_user(username="taller-gallery")
    jefe.groups.add(Group.objects.get_or_create(name="JEFE_TALLER")[0])
    api.force_authenticate(jefe)
    assert api.get(image["url"]).status_code == 404
    assert api.get(f"/api/v1/imagenes-privadas/?detalle={detalle}").status_code == 404
    aprobar_proforma(proforma_id=result.data["id"], actor=user)
    assert api.get(f"/api/v1/imagenes-privadas/?detalle={detalle}").status_code == 200
    response = api.get(image["url"])
    assert response.status_code == 200
    response.close()
    other = vendedor(django_user_model.objects.create_user(username="linked-other-gallery"))
    api.force_authenticate(other)
    assert api.get(image["url"]).status_code == 404
    assert api.get(path).status_code == 404


def test_migraciones_conservan_fotografias_existentes(ctx):
    from importlib import import_module

    from django.apps import apps
    from django.core.files.storage import default_storage

    from apps.media.services import guardar_imagen
    from apps.proformas.services import agregar_detalle, crear_proforma
    from tests.factories import cliente_persona, valor

    user, _ = ctx
    p = silla(user, sku="LEGACY-GALLERY")
    key, variantes, dimensiones, _, _ = guardar_imagen(foto(), prefijo="productos/")
    p.imagen_principal = key
    p.imagen_principal_variantes = variantes
    p.imagen_principal_dimensiones = dimensiones
    p.save()
    import_module("apps.catalogo.migrations.0011_conservar_galerias").conservar(apps, None)
    assert p.imagenes.get().ruta_storage == key
    assert default_storage.exists(key)
    proforma = crear_proforma(actor=user, cliente=cliente_persona(user))
    detalle = agregar_detalle(
        proforma_id=proforma.pk,
        actor=user,
        tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
        nombre="Legado",
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=100,
    )
    legacy_key, variants, dims, mime, size = guardar_imagen(foto("blue"), prefijo="proformas/")
    adjunto = ArchivoAdjunto.objects.create(
        proforma=proforma,
        proforma_detalle=detalle,
        nombre="Legado",
        nombre_storage="original.webp",
        ruta_storage=legacy_key,
        mime_type=mime,
        tamano_bytes=size,
    )
    import_module("apps.documentos.migrations.0007_proteger_adjuntos_existentes").proteger(
        apps, None
    )
    import_module("apps.documentos.migrations.0008_ordenar_legado").ordenar(apps, None)
    adjunto.refresh_from_db()
    assert adjunto.privado and adjunto.principal
    assert privado().exists(adjunto.ruta_storage)
    assert not default_storage.exists(legacy_key)
    assert adjunto.proforma_detalle_id == detalle.pk


def test_encargado_gestiona_catalogo_sin_ampliar_su_acceso_comercial(ctx, django_user_model):
    from django.contrib.auth.models import Group

    from tests.api.test_ap5_catalogo_documentos import payload

    _, api = ctx
    encargado = django_user_model.objects.create_user(username="encargado-gallery")
    encargado.groups.add(Group.objects.get_or_create(name="ENCARGADO_TIENDA")[0])
    api.force_authenticate(encargado)
    result = api.post(
        "/api/v1/catalogo/productos/", payload("OTRO", "BARRA", "ENC-GALLERY"), format="json"
    )
    assert result.status_code == 201, result.data
    subir(api, f"/api/v1/catalogo/productos/{result.data['id']}/imagenes/")
    assert api.get("/api/v1/proformas/").status_code == 403
