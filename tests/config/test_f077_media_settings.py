import importlib
import sys

import pytest

MEDIA_ENV = (
    "HOMEX_MEDIA_STORAGE",
    "HOMEX_MEDIA_ROOT",
    "HOMEX_MEDIA_URL",
    "HOMEX_HTTPS_ENABLED",
    "R2_BUCKET_NAME",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_ENDPOINT_URL",
    "HOMEX_MEDIA_PUBLIC_DOMAIN",
)


def _recargar_produccion():
    sys.modules.pop("config.settings.production", None)
    return importlib.import_module("config.settings.production")


def _limpiar_media_env(monkeypatch):
    for name in MEDIA_ENV:
        monkeypatch.delenv(name, raising=False)


def test_produccion_filesystem_es_default_y_exige_media_root(monkeypatch):
    _limpiar_media_env(monkeypatch)

    with pytest.raises(
        RuntimeError,
        match="Variable de entorno requerida: HOMEX_MEDIA_ROOT",
    ):
        _recargar_produccion()


def test_produccion_filesystem_no_exige_r2(monkeypatch, tmp_path):
    _limpiar_media_env(monkeypatch)
    monkeypatch.setenv("HOMEX_MEDIA_ROOT", str(tmp_path / "media"))

    production = _recargar_produccion()

    assert production.HOMEX_MEDIA_STORAGE == "filesystem"
    assert production.MEDIA_ROOT == tmp_path / "media"
    assert production.MEDIA_URL == "/media/"
    assert (
        production.STORAGES["default"]["BACKEND"] == "django.core.files.storage.FileSystemStorage"
    )
    assert production.SECURE_SSL_REDIRECT is False


def test_produccion_rechaza_media_root_relativo(monkeypatch):
    _limpiar_media_env(monkeypatch)
    monkeypatch.setenv("HOMEX_MEDIA_ROOT", "media-relativa")

    with pytest.raises(RuntimeError, match="HOMEX_MEDIA_ROOT debe ser una ruta absoluta"):
        _recargar_produccion()


def test_produccion_s3_falla_si_falta_variable_obligatoria(monkeypatch):
    _limpiar_media_env(monkeypatch)
    monkeypatch.setenv("HOMEX_MEDIA_STORAGE", "s3")
    monkeypatch.setenv("R2_BUCKET_NAME", "homex-public-media")

    with pytest.raises(
        RuntimeError,
        match="Variable de entorno requerida: R2_ACCESS_KEY_ID",
    ):
        _recargar_produccion()


def test_produccion_s3_rechaza_bucket_distinto(monkeypatch):
    _limpiar_media_env(monkeypatch)
    monkeypatch.setenv("HOMEX_MEDIA_STORAGE", "s3")
    monkeypatch.setenv("R2_BUCKET_NAME", "bucket-equivocado")

    with pytest.raises(
        RuntimeError,
        match="R2_BUCKET_NAME debe ser homex-public-media",
    ):
        _recargar_produccion()


def test_produccion_s3_conserva_backend_r2(monkeypatch):
    _limpiar_media_env(monkeypatch)
    valores = {
        "HOMEX_MEDIA_STORAGE": "s3",
        "R2_BUCKET_NAME": "homex-public-media",
        "R2_ACCESS_KEY_ID": "access-test",
        "R2_SECRET_ACCESS_KEY": "secret-test",
        "R2_ENDPOINT_URL": "https://example.r2.cloudflarestorage.com",
        "HOMEX_MEDIA_PUBLIC_DOMAIN": "media.example.com",
    }
    for name, value in valores.items():
        monkeypatch.setenv(name, value)

    production = _recargar_produccion()
    options = production.STORAGES["default"]["OPTIONS"]

    assert production.STORAGES["default"]["BACKEND"] == "storages.backends.s3.S3Storage"
    assert options["bucket_name"] == "homex-public-media"
    assert options["custom_domain"] == "media.example.com"
    assert options["querystring_auth"] is False
    assert options["file_overwrite"] is False
    assert "default_acl" not in options


def test_produccion_rechaza_storage_desconocido(monkeypatch):
    _limpiar_media_env(monkeypatch)
    monkeypatch.setenv("HOMEX_MEDIA_STORAGE", "otro")

    with pytest.raises(RuntimeError, match="HOMEX_MEDIA_STORAGE debe ser 'filesystem' o 's3'"):
        _recargar_produccion()


def test_https_productivo_es_configurable(monkeypatch, tmp_path):
    _limpiar_media_env(monkeypatch)
    monkeypatch.setenv("HOMEX_MEDIA_ROOT", str(tmp_path / "media"))
    monkeypatch.setenv("HOMEX_HTTPS_ENABLED", "true")

    production = _recargar_produccion()

    assert production.SECURE_SSL_REDIRECT is True
    assert production.SESSION_COOKIE_SECURE is True
    assert production.CSRF_COOKIE_SECURE is True
    assert production.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")


def test_openapi_no_expone_configuracion_interna_de_storage():
    schema = open("docs/openapi.yaml", encoding="utf-8").read()

    prohibidos = [
        "HOMEX_MEDIA_ROOT",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_ENDPOINT_URL",
        "homex-public-media",
        "cloudflarestorage.com",
    ]

    for valor in prohibidos:
        assert valor not in schema
