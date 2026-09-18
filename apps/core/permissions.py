from rest_framework.permissions import BasePermission

NOMBRE_GRUPO_VENDEDOR = "VENDEDOR"


def es_vendedor(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (
            user.is_superuser
            or user.is_staff
            or user.groups.filter(name=NOMBRE_GRUPO_VENDEDOR).exists()
        )
    )


class EsVendedor(BasePermission):
    message = "Se requiere el rol VENDEDOR para operar el flujo comercial."

    def has_permission(self, request, view) -> bool:
        return es_vendedor(request.user)


class EsAdministradorComercial(EsVendedor):
    message = "Esta operación requiere administración comercial."

    def has_permission(self, request, view) -> bool:
        return bool(
            super().has_permission(request, view)
            and (request.user.is_staff or request.user.is_superuser)
        )
