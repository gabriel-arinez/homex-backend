from rest_framework.permissions import BasePermission

NOMBRE_GRUPO_ENCARGADO_TIENDA = "ENCARGADO_TIENDA"
NOMBRE_GRUPO_VENDEDOR = "VENDEDOR"
NOMBRE_GRUPO_JEFE_TALLER = "JEFE_TALLER"
GRUPOS_OPERACION_TIENDA = (NOMBRE_GRUPO_ENCARGADO_TIENDA, NOMBRE_GRUPO_VENDEDOR)

CAPACIDAD_OPERAR_COMERCIAL = "comercial.operar"
CAPACIDAD_ADMINISTRAR_COMERCIAL = "comercial.administrar"
CAPACIDAD_OPERAR_TALLER = "taller.operar"
CAPACIDAD_CREAR_PRODUCTO = "catalogo.crear_producto"


def es_encargado_tienda(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (
            user.is_superuser
            or user.is_staff
            or user.groups.filter(name__in=GRUPOS_OPERACION_TIENDA).exists()
        )
    )


def es_vendedor(user) -> bool:
    """Alias de compatibilidad progresiva: ENCARGADO_TIENDA consolida el perfil comercial."""
    return es_encargado_tienda(user)


def es_administrador_comercial(user) -> bool:
    return bool(es_encargado_tienda(user) and (user.is_staff or user.is_superuser))


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


def puede_crear_producto(user) -> bool:
    return es_encargado_tienda(user)


def capacidades_usuario(user) -> list[str]:
    capacidades = []

    if es_encargado_tienda(user):
        capacidades.append(CAPACIDAD_OPERAR_COMERCIAL)

    if es_administrador_comercial(user):
        capacidades.append(CAPACIDAD_ADMINISTRAR_COMERCIAL)

    if es_jefe_taller(user):
        capacidades.append(CAPACIDAD_OPERAR_TALLER)

    if puede_crear_producto(user):
        capacidades.append(CAPACIDAD_CREAR_PRODUCTO)

    return capacidades


class EsEncargadoTienda(BasePermission):
    message = "Se requiere el rol ENCARGADO_TIENDA para operar el flujo comercial."

    def has_permission(self, request, view) -> bool:
        return es_encargado_tienda(request.user)


class EsVendedor(EsEncargadoTienda):
    """Clase de compatibilidad que delega en EsEncargadoTienda."""


class EsAdministradorComercial(EsEncargadoTienda):
    message = "Esta operación requiere administración comercial."

    def has_permission(self, request, view) -> bool:
        return es_administrador_comercial(request.user)


class EsOperadorOrdenTrabajo(BasePermission):
    message = "Se requiere el rol ENCARGADO_TIENDA o JEFE_TALLER para consultar órdenes de trabajo."

    def has_permission(self, request, view) -> bool:
        return es_encargado_tienda(request.user) or es_jefe_taller(request.user)


class PuedeCrearProducto(BasePermission):
    message = "Se requiere permiso para crear productos de catálogo."

    def has_permission(self, request, view) -> bool:
        return puede_crear_producto(request.user)


class PuedeLeerCatalogo(BasePermission):
    def has_permission(self, request, view) -> bool:
        return es_encargado_tienda(request.user)
