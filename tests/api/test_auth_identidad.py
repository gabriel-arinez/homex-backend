import pytest
from rest_framework.test import APIClient

from tests.factories import vendedor

URL_TOKEN = "/api/v1/auth/token/"
URL_ME = "/api/v1/auth/me/"
PASSWORD = "HomexTest123!"


def autenticar(cliente, username):
    respuesta = cliente.post(
        URL_TOKEN,
        {
            "username": username,
            "password": PASSWORD,
        },
        format="json",
    )

    assert respuesta.status_code == 200
    assert "access" in respuesta.data

    cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {respuesta.data['access']}")


@pytest.mark.django_db
def test_identidad_requiere_autenticacion():
    cliente = APIClient()

    respuesta = cliente.get(URL_ME)

    assert respuesta.status_code == 401


@pytest.mark.django_db
def test_identidad_vendedor(django_user_model):
    user = django_user_model.objects.create_user(
        username="auth-vendedor",
        password=PASSWORD,
        first_name="Ana",
        last_name="Pérez",
    )
    vendedor(user)

    cliente = APIClient()
    autenticar(cliente, user.username)

    respuesta = cliente.get(URL_ME)

    assert respuesta.status_code == 200
    assert respuesta.data == {
        "id": user.id,
        "username": "auth-vendedor",
        "display_name": "Ana Pérez",
        "capabilities": ["comercial.operar"],
    }


@pytest.mark.django_db
def test_identidad_administrador(django_user_model):
    user = django_user_model.objects.create_user(
        username="auth-admin",
        password=PASSWORD,
        is_staff=True,
    )

    cliente = APIClient()
    autenticar(cliente, user.username)

    respuesta = cliente.get(URL_ME)

    assert respuesta.status_code == 200
    assert respuesta.data == {
        "id": user.id,
        "username": "auth-admin",
        "display_name": "auth-admin",
        "capabilities": [
            "comercial.operar",
            "comercial.administrar",
        ],
    }


@pytest.mark.django_db
def test_identidad_usuario_sin_rol(django_user_model):
    user = django_user_model.objects.create_user(
        username="auth-sin-rol",
        password=PASSWORD,
    )

    cliente = APIClient()
    autenticar(cliente, user.username)

    respuesta = cliente.get(URL_ME)

    assert respuesta.status_code == 200
    assert respuesta.data == {
        "id": user.id,
        "username": "auth-sin-rol",
        "display_name": "auth-sin-rol",
        "capabilities": [],
    }
