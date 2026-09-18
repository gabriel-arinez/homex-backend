from django.db import transaction

from apps.clientes.models import Cliente


@transaction.atomic
def crear_cliente(*, actor, **datos) -> Cliente:
    return Cliente.objects.create(created_by=actor, updated_by=actor, **datos)


@transaction.atomic
def actualizar_cliente(*, cliente: Cliente, actor, **datos) -> Cliente:
    for campo, valor in datos.items():
        setattr(cliente, campo, valor)
    cliente.updated_by = actor
    cliente.save()
    return cliente
