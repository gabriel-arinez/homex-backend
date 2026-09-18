import pytest
from rest_framework.test import APIClient

from tests.factories import vendedor


@pytest.mark.django_db
def test_cliente_exige_vendedor_y_aísla_registros(django_user_model):
    sin_rol = django_user_model.objects.create_user(username="sin-rol")
    propietario = vendedor(django_user_model.objects.create_user(username="propietario"))
    ajeno = vendedor(django_user_model.objects.create_user(username="ajeno"))
    cliente = APIClient()

    cliente.force_authenticate(sin_rol)
    respuesta = cliente.get("/api/v1/clientes/")
    assert respuesta.status_code == 403

    cliente.force_authenticate(propietario)
    respuesta = cliente.post(
        "/api/v1/clientes/",
        {"tipo_cliente": 1, "nombres": "Ana", "apellidos": "López"},
        format="json",
    )
    assert respuesta.status_code == 201

    from tests.factories import cliente_persona

    registro = cliente_persona(propietario)
    cliente.force_authenticate(ajeno)
    respuesta = cliente.get(f"/api/v1/clientes/{registro.id}/")
    assert respuesta.status_code == 404
