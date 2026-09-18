from rest_framework.permissions import BasePermission

from apps.accounts.roles import ADMINISTRATION, SALES, has_any_role


class IsSalesOrAdministration(BasePermission):
    message = "Se requiere el rol de ventas o administración."

    def has_permission(self, request, view) -> bool:
        return has_any_role(request.user, SALES, ADMINISTRATION)
