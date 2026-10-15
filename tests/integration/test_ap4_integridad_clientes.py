import pytest
from django.db import DatabaseError

from apps.clientes.models import Cliente
from tests.factories import cliente_persona, valor, vendedor


@pytest.mark.django_db(transaction=True)
def test_ap4_postgresql_protege_identidad_y_tipo_inmutable(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap4-db"))
    with pytest.raises(DatabaseError, match="registrar nombres"):
        Cliente.objects.create(
            tipo_cliente=valor("TIPO_CLIENTE", "PERSONA"),
            nombres=" ",
            apellidos="López",
            created_by=actor,
            updated_by=actor,
        )

    registro = cliente_persona(actor)
    registro.tipo_cliente = valor("TIPO_CLIENTE", "EMPRESA")
    registro.empresa = "Empresa"
    with pytest.raises(DatabaseError, match="inmutable"):
        registro.save()
