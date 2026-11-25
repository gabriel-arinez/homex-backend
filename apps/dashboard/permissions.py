from rest_framework.permissions import BasePermission

from apps.core.permissions import (
    EsAdministradorComercial,
    EsEncargadoTienda,
    es_jefe_taller,
)


class EsJefeTaller(BasePermission):
    message = "Se requiere el rol JEFE_TALLER para acceder al dashboard de taller."

    def has_permission(self, request, view) -> bool:
        return es_jefe_taller(request.user)


__all__ = [
    "EsAdministradorComercial",
    "EsEncargadoTienda",
    "EsJefeTaller",
]
