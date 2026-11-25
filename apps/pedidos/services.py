from django.db import DatabaseError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.exceptions import ConflictoComercial
from apps.core.permissions import es_jefe_taller
from apps.core.tiempo_comercial import fecha_comercial_actual, fecha_hora_comercial_simulada
from apps.notas_entrega.models import NotaEntrega
from apps.notas_entrega.services import emitir_nota
from apps.ordenes_trabajo.models import OrdenTrabajo
from apps.ordenes_trabajo.services import registrar_historial_estado_orden_trabajo
from apps.pedidos.models import Pedido
from apps.proformas.services import _proforma_bloqueada, valor_catalogo
from apps.proformas.vigencia import esta_vencida


def _traducir_error_comercial_postgresql(
    exc: DatabaseError,
    campo: str,
    *,
    conflicto: bool = False,
):
    """
    Los RAISE EXCEPTION de los triggers comerciales PostgreSQL
    utilizan SQLSTATE P0001.

    Sólo esos errores esperados del dominio se convierten en
    ValidationError. Los errores técnicos conservan su excepción.
    """
    causa = exc.__cause__
    sqlstate = getattr(causa, "sqlstate", None)

    if sqlstate == "P0001":
        mensaje = str(causa).splitlines()[0]

        excepcion = ConflictoComercial if conflicto else ValidationError
        raise excepcion(
            {
                campo: mensaje,
            }
        ) from exc

    raise exc


@transaction.atomic
def aprobar_proforma(
    *,
    proforma_id,
    actor,
):
    proforma = _proforma_bloqueada(
        proforma_id,
        actor,
    )

    if proforma.estado.codigo not in {"EN_REVISION", "ENVIADA"}:
        raise ConflictoComercial(
            {"estado": "Sólo una proforma EN_REVISION (o ENVIADA histórica) puede aprobarse."}
        )

    if (
        proforma.validez_oferta
        and proforma.validez_oferta > 0
        and esta_vencida(
            proforma.fecha, proforma.validez_oferta, fecha_comercial_actual(timezone.localdate)
        )
    ):
        raise ConflictoComercial({"estado": "La proforma ha vencido y no puede aprobarse."})

    proforma.estado = valor_catalogo(
        "ESTADO_PROFORMA",
        "APROBADA",
    )
    proforma.ultima_actividad_comercial = fecha_hora_comercial_simulada() or timezone.now()
    proforma.updated_by = actor

    try:
        # PostgreSQL es la autoridad:
        # APROBADA -> pedido -> VENTA -> stock -> OT.
        proforma.save(
            update_fields=[
                "estado",
                "ultima_actividad_comercial",
                "updated_by",
            ]
        )
    except DatabaseError as exc:
        _traducir_error_comercial_postgresql(
            exc,
            "aprobacion",
            conflicto=True,
        )

    pedido = Pedido.objects.select_related(
        "proforma",
        "estado",
    ).get(
        proforma=proforma,
    )
    ot = OrdenTrabajo.objects.filter(pedido=pedido).select_related("estado").first()
    if ot is not None:
        registrar_historial_estado_orden_trabajo(
            orden_trabajo=ot,
            estado_anterior=None,
            estado_nuevo=ot.estado,
            actor=actor,
            observaciones="Creación automática de orden de trabajo.",
        )
    return pedido


@transaction.atomic
def cambiar_estado_pedido(
    *,
    pedido_id,
    actor,
    estado_codigo,
):
    """
    Avanza el ciclo normal de un pedido.

    PostgreSQL sigue siendo la autoridad sobre las transiciones válidas
    mediante transiciones_estado_pedido y trg_validar_transicion_pedido.

    CANCELADO se procesa exclusivamente mediante cancelar_pedido(),
    porque esa acción aplica las reglas comerciales de cancelación.
    """
    try:
        pedido = (
            Pedido.objects.select_for_update()
            .select_related(
                "proforma",
                "estado",
            )
            .get(
                pk=pedido_id,
            )
        )
    except Pedido.DoesNotExist as exc:
        raise ValidationError(
            {
                "pedido": "El pedido no existe.",
            }
        ) from exc

    es_taller_listo = es_jefe_taller(actor) and estado_codigo == "LISTO_ENTREGA"
    if (
        pedido.proforma.vendedor_id != actor.id
        and not (actor.is_staff or actor.is_superuser)
        and not es_taller_listo
    ):
        raise ValidationError(
            {
                "pedido": "No puede modificar un pedido ajeno.",
            }
        )

    if estado_codigo == "CANCELADO":
        raise ValidationError(
            {
                "estado": (
                    "La cancelación debe realizarse mediante la acción específica cancelar."
                ),
            }
        )

    tiene_muebles = pedido.proforma.detalles.filter(
        tipo_item__concepto__codigo="TIPO_ITEM",
        tipo_item__codigo="MUEBLE_MEDIDA",
    ).exists()
    if pedido.estado.codigo == "CONFIRMADO" and estado_codigo == "LISTO_ENTREGA":
        if tiene_muebles:
            raise ValidationError(
                {"estado": "Un pedido con muebles a medida debe pasar por EN_PRODUCCION."}
            )
    if estado_codigo == "LISTO_ENTREGA" and tiene_muebles:
        ots_no_terminadas = (
            OrdenTrabajo.objects.filter(pedido=pedido)
            .exclude(estado__codigo__in=["TERMINADA", "CANCELADA"])
            .exists()
        )
        tiene_ot_terminada = OrdenTrabajo.objects.filter(
            pedido=pedido,
            estado__codigo="TERMINADA",
        ).exists()
        if ots_no_terminadas or not tiene_ot_terminada:
            raise ValidationError(
                {
                    "estado": (
                        "No puede marcar el pedido como LISTO_ENTREGA mientras existan "
                        "órdenes de trabajo sin terminar."
                    )
                }
            )
    if pedido.estado.codigo == "CONFIRMADO" and estado_codigo == "EN_PRODUCCION":
        if not tiene_muebles:
            raise ValidationError(
                {"estado": "Un pedido sólo de catálogo pasa directamente a LISTO_ENTREGA."}
            )

    pedido.estado = valor_catalogo(
        "ESTADO_PEDIDO",
        estado_codigo,
    )
    pedido.updated_by = actor

    try:
        # PostgreSQL valida la transición configurada.
        pedido.save(
            update_fields=[
                "estado",
                "updated_by",
            ]
        )
    except DatabaseError as exc:
        _traducir_error_comercial_postgresql(
            exc,
            "estado",
        )

    pedido.refresh_from_db()

    if estado_codigo == "EN_PRODUCCION":
        hoy = fecha_comercial_actual(timezone.localdate)
        estado_en_proceso = valor_catalogo("ESTADO_ORDEN_TRABAJO", "EN_PROCESO")
        for ot in OrdenTrabajo.objects.filter(
            pedido=pedido,
            estado__codigo="PENDIENTE",
        ).select_related("estado"):
            estado_ant = ot.estado
            ot.estado = estado_en_proceso
            ot.updated_by = actor
            update_ot = ["estado", "updated_by"]
            if ot.fecha_inicio is None:
                ot.fecha_inicio = hoy
                update_ot.append("fecha_inicio")
            ot.save(update_fields=update_ot)
            registrar_historial_estado_orden_trabajo(
                orden_trabajo=ot,
                estado_anterior=estado_ant,
                estado_nuevo=estado_en_proceso,
                actor=actor,
                observaciones="Inicio de producción del pedido.",
            )
        OrdenTrabajo.objects.filter(
            pedido=pedido,
            fecha_inicio__isnull=True,
        ).update(
            fecha_inicio=hoy,
            updated_by=actor,
        )
    elif estado_codigo == "LISTO_ENTREGA":
        from django.db.models import Q

        hoy = fecha_comercial_actual(timezone.localdate)
        if not tiene_muebles:
            estado_terminada = valor_catalogo("ESTADO_ORDEN_TRABAJO", "TERMINADA")
            for ot in (
                OrdenTrabajo.objects.filter(pedido=pedido)
                .exclude(estado__codigo__in=["TERMINADA", "CANCELADA"])
                .select_related("estado")
            ):
                estado_ant = ot.estado
                ot.estado = estado_terminada
                ot.updated_by = actor
                ot.save(update_fields=["estado", "updated_by"])
                registrar_historial_estado_orden_trabajo(
                    orden_trabajo=ot,
                    estado_anterior=estado_ant,
                    estado_nuevo=estado_terminada,
                    actor=actor,
                    observaciones="Preparación de catálogo lista para entrega.",
                )
        OrdenTrabajo.objects.filter(
            pedido=pedido,
            fecha_fin__isnull=True,
        ).filter(
            Q(fecha_inicio__isnull=True) | Q(fecha_inicio__lte=hoy),
        ).update(
            fecha_fin=hoy,
            updated_by=actor,
        )
        if not NotaEntrega.objects.filter(pedido=pedido).exists():
            emitir_nota(pedido=pedido, actor=actor, permitir_taller=es_taller_listo)
    elif estado_codigo == "ENTREGADO" and pedido.fecha_entrega_efectiva is None:
        pedido.fecha_entrega_efectiva = fecha_comercial_actual(timezone.localdate)
        pedido.save(update_fields=["fecha_entrega_efectiva"])

    return pedido


@transaction.atomic
def cancelar_pedido(
    *,
    pedido_id,
    actor,
):
    try:
        pedido = (
            Pedido.objects.select_for_update()
            .select_related(
                "proforma",
                "estado",
            )
            .get(
                pk=pedido_id,
            )
        )
    except Pedido.DoesNotExist as exc:
        raise ValidationError(
            {
                "pedido": "El pedido no existe.",
            }
        ) from exc

    if pedido.proforma.vendedor_id != actor.id and not (actor.is_staff or actor.is_superuser):
        raise ValidationError({"pedido": ("No puede cancelar un pedido ajeno.")})

    if pedido.estado.codigo == "CANCELADO":
        raise ValidationError({"estado": ("El pedido ya está cancelado.")})

    pedido.estado = valor_catalogo(
        "ESTADO_PEDIDO",
        "CANCELADO",
    )
    pedido.updated_by = actor

    try:
        # PostgreSQL genera las REVERSA_VENTA
        # y cancela la OT.
        pedido.save(
            update_fields=[
                "estado",
                "updated_by",
            ]
        )
    except DatabaseError as exc:
        _traducir_error_comercial_postgresql(
            exc,
            "cancelacion",
        )

    pedido.refresh_from_db()
    for ot in OrdenTrabajo.objects.filter(pedido=pedido, estado__codigo="CANCELADA").select_related(
        "estado"
    ):
        if not ot.historial_estados.filter(estado_nuevo__codigo="CANCELADA").exists():
            estado_ant = (
                ot.historial_estados.order_by("-fecha", "-id").first().estado_nuevo
                if ot.historial_estados.exists()
                else None
            )
            registrar_historial_estado_orden_trabajo(
                orden_trabajo=ot,
                estado_anterior=estado_ant,
                estado_nuevo=ot.estado,
                actor=actor,
                observaciones="Cancelación automática por cancelación del pedido.",
            )

    return pedido
