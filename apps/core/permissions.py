from rest_framework.permissions import BasePermission

NOMBRE_GRUPO_VENDEDOR = "VENDEDOR"
NOMBRE_GRUPO_JEFE_TALLER = "JEFE_TALLER"

CAPACIDAD_OPERAR_COMERCIAL = "comercial.operar"
CAPACIDAD_ADMINISTRAR_COMERCIAL = "comercial.administrar"
CAPACIDAD_OPERAR_TALLER = "taller.operar"


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


def es_administrador_comercial(user) -> bool:
    return bool(es_vendedor(user) and (user.is_staff or user.is_superuser))


def es_jefe_taller(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (
            user.is_superuser
            or user.is_staff
            or user.groups.filter(name=NOMBRE_GRUPO_JEFE_TALLER).exists()
        )
    )


def capacidades_usuario(user) -> list[str]:
    capacidades = []

    if es_vendedor(user):
        capacidades.append(CAPACIDAD_OPERAR_COMERCIAL)

    if es_administrador_comercial(user):
        capacidades.append(CAPACIDAD_ADMINISTRAR_COMERCIAL)

    if es_jefe_taller(user):
        capacidades.append(CAPACIDAD_OPERAR_TALLER)

    return capacidades


class EsVendedor(BasePermission):
    message = "Se requiere el rol VENDEDOR para operar el flujo comercial."

    def has_permission(self, request, view) -> bool:
        return es_vendedor(request.user)


class EsAdministradorComercial(EsVendedor):
    message = "Esta operación requiere administración comercial."

    def has_permission(self, request, view) -> bool:
        return es_administrador_comercial(request.user)


class EsOperadorOrdenTrabajo(BasePermission):
    message = "Se requiere un rol comercial o JEFE_TALLER para consultar órdenes de trabajo."

    def has_permission(self, request, view) -> bool:
        return es_vendedor(request.user) or es_jefe_taller(request.user)
