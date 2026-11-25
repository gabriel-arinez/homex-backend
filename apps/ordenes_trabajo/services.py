from django.db import DatabaseError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.catalogo.models import ValorCatalogo
from apps.core.db_errors import traducir_error_comercial_postgresql
from apps.core.exceptions import ConflictoComercial
from apps.core.permissions import NOMBRE_GRUPO_JEFE_TALLER
from apps.core.tiempo_comercial import fecha_comercial_actual, fecha_hora_comercial_simulada
from apps.ordenes_trabajo.models import HistorialEstadoOrdenTrabajo, OrdenTrabajo
from apps.pedidos.models import Pedido

# Una OT no puede cancelarse de forma independiente mientras su pedido siga activo;
# únicamente se cancela en cascada al cancelar el pedido mediante cancelar_pedido().
TRANSICIONES_OT_PERMITIDAS = {
    "PENDIENTE": {"EN_PROCESO"},
    "EN_PROCESO": {"TERMINADA"},
    "TERMINADA": set(),
    "CANCELADA": set(),
}


def puede_cambiar_estado_orden_trabajo(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or user.groups.filter(name=NOMBRE_GRUPO_JEFE_TALLER).exists())
    )


def registrar_historial_estado_orden_trabajo(
    *,
    orden_trabajo: OrdenTrabajo,
    estado_anterior,
    estado_nuevo,
    actor,
    observaciones: str | None = None,
    fecha=None,
) -> HistorialEstadoOrdenTrabajo:
    fecha_evento = fecha or fecha_hora_comercial_simulada() or timezone.now()
    return HistorialEstadoOrdenTrabajo.objects.create(
        orden_trabajo=orden_trabajo,
        estado_anterior=estado_anterior,
        estado_nuevo=estado_nuevo,
        cambiado_por=actor,
        fecha=fecha_evento,
        observaciones=(observaciones or "").strip() or None,
    )


@transaction.atomic
def cambiar_estado_orden_trabajo(
    *,
    orden_trabajo_id: int,
    actor,
    estado_codigo: str,
    observaciones: str | None = None,
) -> OrdenTrabajo:
    if not puede_cambiar_estado_orden_trabajo(actor):
        raise PermissionDenied(
            "Solo el rol JEFE_TALLER puede cambiar el estado de una orden de trabajo."
        )

    pedido_id = (
        OrdenTrabajo.objects.filter(pk=orden_trabajo_id).values_list("pedido_id", flat=True).first()
    )
    if pedido_id is None:
        raise ValidationError({"orden_trabajo": "La orden de trabajo no existe."})

    # Orden determinista de locks: Pedido -> OrdenTrabajo para evitar deadlocks.
    pedido = Pedido.objects.select_for_update().select_related("estado").get(pk=pedido_id)
    orden = (
        OrdenTrabajo.objects.select_for_update()
        .select_related("estado", "pedido__estado")
        .get(pk=orden_trabajo_id)
    )

    codigo_actual = orden.estado.codigo
    destino = (estado_codigo or "").strip().upper()
    if destino not in TRANSICIONES_OT_PERMITIDAS:
        raise ValidationError({"estado_codigo": f"Estado de orden inválido: {estado_codigo}."})

    if codigo_actual == destino:
        return orden

    permitidos = TRANSICIONES_OT_PERMITIDAS.get(codigo_actual, set())
    if destino not in permitidos:
        raise ConflictoComercial(
            f"Transición de orden de trabajo no permitida: {codigo_actual} -> {destino}."
        )

    estado_anterior = orden.estado
    estado_nuevo = ValorCatalogo.objects.get(
        concepto__codigo="ESTADO_ORDEN_TRABAJO", codigo=destino
    )
    hoy = fecha_comercial_actual(timezone.localdate)

    orden.estado = estado_nuevo
    orden.updated_by = actor
    update_fields = ["estado", "updated_by"]

    if destino == "EN_PROCESO" and orden.fecha_inicio is None:
        orden.fecha_inicio = hoy
        update_fields.append("fecha_inicio")
    elif destino == "TERMINADA":
        if orden.fecha_inicio is None:
            orden.fecha_inicio = hoy
            update_fields.append("fecha_inicio")
        if orden.fecha_fin is None:
            orden.fecha_fin = hoy if orden.fecha_inicio <= hoy else orden.fecha_inicio
            update_fields.append("fecha_fin")

    try:
        orden.save(update_fields=update_fields)
    except DatabaseError as exc:
        traducir_error_comercial_postgresql(exc, "estado_codigo", conflicto=True)

    registrar_historial_estado_orden_trabajo(
        orden_trabajo=orden,
        estado_anterior=estado_anterior,
        estado_nuevo=estado_nuevo,
        actor=actor,
        observaciones=observaciones,
    )

    # Sincronización inversa: al iniciar la OT, el pedido CONFIRMADO pasa a EN_PRODUCCION.
    if destino == "EN_PROCESO" and pedido.estado.codigo == "CONFIRMADO":
        pedido.estado = ValorCatalogo.objects.get(
            concepto__codigo="ESTADO_PEDIDO", codigo="EN_PRODUCCION"
        )
        pedido.updated_by = actor
        pedido.save(update_fields=["estado", "updated_by"])

    orden.refresh_from_db()
    return orden
