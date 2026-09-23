from __future__ import annotations

from io import BytesIO
from pathlib import PurePosixPath
from uuid import uuid4

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import ValidationError

VALID_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
VARIANT_WIDTHS = (320, 640, 1280)


def _error(message: str) -> ValidationError:
    return ValidationError({"archivo": message})


def guardar_imagen(archivo, *, prefijo: str) -> tuple[str, dict[str, str], str, int]:
    if not prefijo.endswith("/"):
        raise ValueError("El prefijo de media debe terminar en '/'.")
    if archivo.size > MAX_UPLOAD_BYTES:
        raise _error("La imagen no puede superar 10 MiB.")
    try:
        imagen = Image.open(archivo)
        if imagen.format not in VALID_FORMATS:
            raise _error("Sólo se aceptan imágenes JPEG, PNG o WebP.")
        imagen = ImageOps.exif_transpose(imagen)
        imagen.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise _error("El contenido cargado no es una imagen válida.") from exc

    if imagen.mode not in {"RGB", "RGBA"}:
        imagen = imagen.convert("RGBA" if "transparency" in imagen.info else "RGB")
    base = f"{prefijo}{uuid4()}"
    guardados: list[str] = []
    try:
        original = _webp(imagen)
        original_key = default_storage.save(f"{base}/original.webp", ContentFile(original))
        guardados.append(original_key)
        variantes: dict[str, str] = {}
        for ancho in VARIANT_WIDTHS:
            if imagen.width < ancho:
                continue
            copia = imagen.copy()
            copia.thumbnail((ancho, imagen.height))
            key = default_storage.save(f"{base}/{ancho}.webp", ContentFile(_webp(copia)))
            guardados.append(key)
            variantes[str(ancho)] = key
        return original_key, variantes, "image/webp", len(original)
    except Exception:
        for key in guardados:
            default_storage.delete(key)
        raise


def _webp(imagen: Image.Image) -> bytes:
    destino = BytesIO()
    imagen.save(destino, format="WEBP", quality=85, method=6)
    return destino.getvalue()


def eliminar_objetos(keys: list[str]) -> None:
    for key in keys:
        if key:
            default_storage.delete(key)


def url_publica(key: str) -> str:
    return default_storage.url(key)


def keys_de_variantes(original_key: str) -> list[str]:
    padre = str(PurePosixPath(original_key).parent)
    return [original_key, *(f"{padre}/{ancho}.webp" for ancho in VARIANT_WIDTHS)]
