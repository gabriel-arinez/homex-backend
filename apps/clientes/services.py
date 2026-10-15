from django.db import transaction

from apps.clientes.models import Cliente


@transaction.atomic
def crear_cliente(*, actor, **datos) -> Cliente:
    return Cliente.objects.create(created_by=actor, updated_by=actor, **datos)


@transaction.atomic
def actualizar_cliente(*, cliente: Cliente, actor, **datos) -> Cliente:
    cliente = Cliente.objects.select_for_update().get(pk=cliente.pk)
    for campo, valor in datos.items():
        setattr(cliente, campo, valor)
    cliente.updated_by = actor
    cliente.save()
    return cliente


@transaction.atomic
def desactivar_cliente(*, cliente: Cliente, actor) -> Cliente:
    cliente = Cliente.objects.select_for_update().get(pk=cliente.pk)
    if cliente.activo:
        cliente.activo = False
        cliente.updated_by = actor
        cliente.save(update_fields=["activo", "updated_by"])
    return cliente
