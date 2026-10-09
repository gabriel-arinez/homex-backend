import os
from pathlib import Path

from .base import *  # noqa: F403
from .base import required


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default

    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False

    raise RuntimeError(f"{name} debe ser booleano (0/1, false/true, no/yes, off/on)")


DEBUG = False

# La primera topología productiva viaja por una red privada cifrada. HTTPS del
# endpoint HTTP se activa únicamente cuando deploy entrega un hostname TLS real.
HOMEX_HTTPS_ENABLED = _env_bool("HOMEX_HTTPS_ENABLED", default=False)
SECURE_SSL_REDIRECT = HOMEX_HTTPS_ENABLED
SESSION_COOKIE_SECURE = HOMEX_HTTPS_ENABLED
CSRF_COOKIE_SECURE = HOMEX_HTTPS_ENABLED
if HOMEX_HTTPS_ENABLED:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

HOMEX_MEDIA_STORAGE = os.getenv("HOMEX_MEDIA_STORAGE", "filesystem").strip().lower()
HOMEX_AUDIO_TEMP_ROOT = Path(required("HOMEX_AUDIO_TEMP_ROOT"))
if not HOMEX_AUDIO_TEMP_ROOT.is_absolute():
    raise RuntimeError("HOMEX_AUDIO_TEMP_ROOT debe ser una ruta absoluta en producción")

if HOMEX_MEDIA_STORAGE == "filesystem":
    MEDIA_ROOT = Path(required("HOMEX_MEDIA_ROOT"))
    if not MEDIA_ROOT.is_absolute():
        raise RuntimeError("HOMEX_MEDIA_ROOT debe ser una ruta absoluta en producción")

    media_root_resuelto = MEDIA_ROOT.resolve(strict=False)
    audio_root_resuelto = HOMEX_AUDIO_TEMP_ROOT.resolve(strict=False)
    if (
        media_root_resuelto == audio_root_resuelto
        or media_root_resuelto in audio_root_resuelto.parents
        or audio_root_resuelto in media_root_resuelto.parents
    ):
        raise RuntimeError("HOMEX_MEDIA_ROOT y HOMEX_AUDIO_TEMP_ROOT deben ser árboles separados")

    MEDIA_URL = os.getenv("HOMEX_MEDIA_URL", "/media/").strip()
    if not MEDIA_URL.startswith("/") or not MEDIA_URL.endswith("/"):
        raise RuntimeError("HOMEX_MEDIA_URL debe ser una ruta absoluta URL terminada en '/'")

    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
elif HOMEX_MEDIA_STORAGE == "s3":
    R2_BUCKET_NAME = required("R2_BUCKET_NAME")
    if R2_BUCKET_NAME != "homex-public-media":
        raise RuntimeError("R2_BUCKET_NAME debe ser homex-public-media")

    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "access_key": required("R2_ACCESS_KEY_ID"),
                "secret_key": required("R2_SECRET_ACCESS_KEY"),
                "bucket_name": R2_BUCKET_NAME,
                "endpoint_url": required("R2_ENDPOINT_URL"),
                "custom_domain": required("HOMEX_MEDIA_PUBLIC_DOMAIN"),
                "querystring_auth": False,
                "file_overwrite": False,
            },
        },
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
else:
    raise RuntimeError("HOMEX_MEDIA_STORAGE debe ser 'filesystem' o 's3'")
