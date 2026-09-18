import pytest
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
