from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError
from django.contrib.auth import get_user_model
from django.urls import resolve
from rest_framework.test import APIClient


def test_health_is_public():
    response = APIClient().get("/api/v1/health/")

    assert response.status_code == 200
    assert response.json() == {"estado": "ok"}


@pytest.mark.django_db
def test_jwt_smoke_issues_access_and_refresh_tokens():
    get_user_model().objects.create_user(username="vendedor", password="clave-segura-123")

    response = APIClient().post(
        "/api/v1/auth/token/",
        {"username": "vendedor", "password": "clave-segura-123"},
        format="json",
    )

    assert response.status_code == 200
    assert set(response.data) == {"access", "refresh"}


def test_jwt_routes_are_registered():
    assert resolve("/api/v1/auth/token/").url_name == "token_obtain_pair"
    assert resolve("/api/v1/auth/token/refresh/").url_name == "token_refresh"


def test_readiness_es_publica_y_comprueba_dependencias(monkeypatch, tmp_path, settings):
    media_root = tmp_path / "media"
    media_root.mkdir()
    settings.MEDIA_ROOT = media_root
    settings.HOMEX_MEDIA_STORAGE = "filesystem"
    monkeypatch.setattr("config.views._postgresql_disponible", lambda: True)

    response = APIClient().get("/api/v1/ready/")

    assert response.status_code == 200
    assert response.json() == {
        "estado": "ok",
        "dependencias": {"postgresql": "ok", "media": "ok"},
    }


def test_readiness_responde_503_sin_filtrar_error_interno(monkeypatch, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media-ausente"
    settings.HOMEX_MEDIA_STORAGE = "filesystem"
    monkeypatch.setattr("config.views._postgresql_disponible", lambda: False)

    response = APIClient().get("/api/v1/ready/")

    assert response.status_code == 503
    assert response.json() == {
        "estado": "no_disponible",
        "dependencias": {"postgresql": "error", "media": "error"},
    }
    contenido = response.content.decode()
    assert "DATABASE_URL" not in contenido
    assert "HOMEX_MEDIA_ROOT" not in contenido


def test_readiness_no_acepta_metodos_con_efectos():
    response = APIClient().post("/api/v1/ready/", {}, format="json")

    assert response.status_code == 405


@pytest.mark.parametrize("error_bucket", [False, True])
def test_readiness_s3_verifica_bucket_y_no_una_key(monkeypatch, settings, error_bucket):
    settings.HOMEX_MEDIA_STORAGE = "s3"
    cliente = Mock()
    if error_bucket:
        cliente.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}},
            "HeadBucket",
        )
    storage = Mock()
    storage.bucket_name = "homex-public-media"
    storage.connection.meta.client = cliente
    monkeypatch.setattr("config.views.default_storage", storage)
    monkeypatch.setattr("config.views._postgresql_disponible", lambda: True)

    response = APIClient().get("/api/v1/ready/")

    assert response.status_code == (503 if error_bucket else 200)
    assert response.json()["dependencias"]["media"] == ("error" if error_bucket else "ok")
    cliente.head_bucket.assert_called_once_with(Bucket="homex-public-media")
    storage.exists.assert_not_called()
    storage.save.assert_not_called()
