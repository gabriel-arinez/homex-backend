import importlib
import sys

import pytest

import config.settings.base as base


def _recargar_produccion():
    sys.modules.pop("config.settings.production", None)
    return importlib.import_module("config.settings.production")


def test_produccion_falla_si_falta_variable_r2_obligatoria(monkeypatch):
    valores = {
        "R2_BUCKET_NAME": "homex-public-media",
    }

    def required(nombre):
        if nombre not in valores:
            raise RuntimeError(f"Variable de entorno requerida: {nombre}")
        return valores[nombre]

    monkeypatch.setattr(base, "required", required)

    with pytest.raises(
        RuntimeError,
        match="Variable de entorno requerida: R2_ACCESS_KEY_ID",
    ):
        _recargar_produccion()


def test_produccion_rechaza_bucket_distinto(monkeypatch):
    def required(nombre):
        if nombre == "R2_BUCKET_NAME":
            return "bucket-equivocado"
        return "valor-prueba"

    monkeypatch.setattr(base, "required", required)

    with pytest.raises(
        RuntimeError,
        match="R2_BUCKET_NAME debe ser homex-public-media",
    ):
        _recargar_produccion()


def test_produccion_configura_r2_sin_acl_por_objeto(monkeypatch):
    valores = {
        "R2_BUCKET_NAME": "homex-public-media",
        "R2_ACCESS_KEY_ID": "access-test",
        "R2_SECRET_ACCESS_KEY": "secret-test",
        "R2_ENDPOINT_URL": "https://example.r2.cloudflarestorage.com",
        "HOMEX_MEDIA_PUBLIC_DOMAIN": "media.example.com",
    }

    monkeypatch.setattr(base, "required", valores.__getitem__)

    production = _recargar_produccion()
    options = production.STORAGES["default"]["OPTIONS"]

    assert production.STORAGES["default"]["BACKEND"] == "storages.backends.s3.S3Storage"
    assert options["bucket_name"] == "homex-public-media"
    assert options["custom_domain"] == "media.example.com"
    assert options["querystring_auth"] is False
    assert options["file_overwrite"] is False
    assert "default_acl" not in options


def test_openapi_no_expone_configuracion_interna_de_r2():
    from pathlib import Path

    schema = Path("docs/openapi.yaml").read_text()

    prohibidos = [
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_ENDPOINT_URL",
        "homex-public-media",
        "cloudflarestorage.com",
    ]

    for valor in prohibidos:
        assert valor not in schema
