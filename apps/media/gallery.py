"""Gallery mutations serialize on the parent row, including empty galleries."""

import hashlib

from django.conf import settings
from rest_framework.exceptions import ValidationError

from apps.media.services import guardar_imagen, url_publica


def limite():
    return getattr(settings, "HOMEX_GALLERY_MAX_IMAGES", 8)


def subir(qs, archivo, crear, *, storage=None, prefijo="productos/"):
    if qs.count() >= limite():
        raise ValidationError({"archivo": f"Se admiten hasta {limite()} imágenes."})
    from apps.media.services import MAX_UPLOAD_BYTES

    if archivo.size > MAX_UPLOAD_BYTES:
        raise ValidationError({"archivo": "La imagen no puede superar 10 MiB."})
    digest = hashlib.sha256()
    for chunk in archivo.chunks():
        digest.update(chunk)
    archivo.seek(0)
    sha = digest.hexdigest()
    if qs.filter(sha256=sha).exists():
        raise ValidationError({"archivo": "Esta imagen ya está en la galería."})
    key, variantes, dimensiones, mime, size = guardar_imagen(
        archivo, prefijo=prefijo, storage=storage
    )
    try:
        return crear(
            nombre=archivo.name[:255],
            ruta_storage=key,
            variantes=variantes,
            dimensiones=dimensiones,
            sha256=sha,
            posicion=(qs.order_by("-posicion").first().posicion + 1 if qs.exists() else 0),
            principal=not qs.exists(),
            mime=mime,
            size=size,
        )
    except Exception:
        from django.core.files.storage import default_storage

        for k in [key, *variantes.values()]:
            (storage or default_storage).delete(k)
        raise


def modificar(qs, datos):
    from apps.media.serializers import ModificarGaleriaSerializer

    serializer = ModificarGaleriaSerializer(data=datos)
    serializer.is_valid(raise_exception=True)
    datos = serializer.validated_data
    qs = qs.all()
    imagenes = list(qs)
    ids = [i.pk for i in imagenes]
    if "orden" in datos:
        orden = datos["orden"]
        if not isinstance(orden, list) or len(orden) != len(ids) or set(orden) != set(ids):
            raise ValidationError({"orden": "Envía todos los identificadores exactamente una vez."})
        for i in imagenes:
            i.posicion = orden.index(i.pk)
            i.save(update_fields=["posicion"])
    if "principal" in datos:
        if datos["principal"] not in ids:
            raise ValidationError({"principal": "La imagen no pertenece a esta galería."})
        qs.update(principal=False)
        qs.filter(pk=datos["principal"]).update(principal=True)
    if "eliminar" in datos:
        if datos["eliminar"] not in ids:
            raise ValidationError({"eliminar": "La imagen no pertenece a esta galería."})
        qs.get(pk=datos["eliminar"]).delete()
        qs = qs.all()
        if not qs.filter(principal=True).exists() and qs.exists():
            i = qs.first()
            i.principal = True
            i.save(update_fields=["principal"])


def publico(i):
    return dict(
        id=i.pk,
        sha256=i.sha256,
        nombre=i.nombre,
        posicion=i.posicion,
        principal=i.principal,
        url=url_publica(i.ruta_storage),
        variantes={w: url_publica(k) for w, k in i.variantes.items()},
        dimensiones=i.dimensiones,
    )


def sincronizar_portada(producto):
    i = producto.imagenes.filter(principal=True).first()
    producto.imagen_principal = i.ruta_storage if i else None
    producto.imagen_principal_variantes = i.variantes if i else {}
    producto.imagen_principal_dimensiones = i.dimensiones if i else {}
    producto.save(
        update_fields=[
            "imagen_principal",
            "imagen_principal_variantes",
            "imagen_principal_dimensiones",
        ]
    )
