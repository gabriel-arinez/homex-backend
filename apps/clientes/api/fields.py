"""Referencia a un cliente comercial con aislamiento opaco por vendedor."""

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from rest_framework import serializers
from rest_framework.exceptions import NotFound

from apps.clientes.models import Cliente


class ClienteVisibleField(serializers.PrimaryKeyRelatedField):
    def __init__(self, **kwargs):
        super().__init__(queryset=Cliente.objects.all(), **kwargs)

    def get_queryset(self):
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        if actor is None or not actor.is_authenticated:
            return Cliente.objects.none()
        queryset = Cliente.objects.all()
        if not (actor.is_staff or actor.is_superuser):
            queryset = queryset.filter(created_by=actor)
        proforma = self.context.get("proforma_actual") or getattr(self.parent, "instance", None)
        # La vinculación antigua inactiva se conserva, pero no puede seleccionarse
        # para una nueva operación ni sustituirse por otro cliente inactivo.
        if proforma is not None and getattr(proforma, "cliente_id", None):
            queryset = queryset.filter(Q(activo=True) | Q(pk=proforma.cliente_id))
        else:
            queryset = queryset.filter(activo=True)
        return queryset

    def to_internal_value(self, data):
        try:
            return self.get_queryset().get(pk=data)
        except (ObjectDoesNotExist, ValueError, TypeError):
            # No distinguir cliente ajeno, inactivo no vinculado o ID inexistente.
            raise NotFound("El cliente no existe.") from None
