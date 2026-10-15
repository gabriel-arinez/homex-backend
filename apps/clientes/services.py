from django.db import transaction

from apps.clientes.models import Cliente
from apps.clientes.revision import revision_cliente
from apps.core.exceptions import ConflictoComercial
from rest_framework.exceptions import ValidationError


@transaction.atomic
def crear_cliente(*, actor, **datos) -> Cliente:
    return Cliente.objects.create(created_by=actor, updated_by=actor, **datos)


def _verificar_revision(cliente: Cliente, revision_esperada: str | None):
    if not revision_esperada:
        raise ValidationError({"revision_esperada": "Debes cargar la última versión del cliente."})
    if revision_esperada != revision_cliente(cliente):
        raise ConflictoComercial({"revision_esperada": "El cliente cambió desde que abriste la ficha."})


@transaction.atomic
def actualizar_cliente(*, cliente: Cliente, actor, revision_esperada=None, **datos) -> Cliente:
    cliente = Cliente.objects.select_for_update().get(pk=cliente.pk)
    _verificar_revision(cliente, revision_esperada)
    for campo, valor in datos.items():
        setattr(cliente, campo, valor)
    cliente.updated_by = actor
    cliente.save()
    return cliente


@transaction.atomic
def desactivar_cliente(*, cliente: Cliente, actor, revision_esperada=None) -> Cliente:
    cliente = Cliente.objects.select_for_update().get(pk=cliente.pk)
    _verificar_revision(cliente, revision_esperada)
    if cliente.activo:
        cliente.activo = False
        cliente.updated_by = actor
        cliente.save(update_fields=["activo", "updated_by"])
    return cliente
