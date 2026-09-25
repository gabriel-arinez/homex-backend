from django.db import DatabaseError, transaction
from rest_framework.exceptions import ValidationError

from apps.core.exceptions import ConflictoComercial
from apps.pedidos.models import Pedido
from apps.proformas.services import _proforma_bloqueada, valor_catalogo


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

    if proforma.estado.codigo != "ENVIADA":
        raise ConflictoComercial({"estado": "Sólo una proforma ENVIADA puede aprobarse."})

    proforma.estado = valor_catalogo(
        "ESTADO_PROFORMA",
        "APROBADA",
    )
    proforma.updated_by = actor

    try:
        # PostgreSQL es la autoridad:
        # APROBADA -> pedido -> VENTA -> stock -> OT.
        proforma.save(
            update_fields=[
                "estado",
                "updated_by",
            ]
        )
    except DatabaseError as exc:
        _traducir_error_comercial_postgresql(
            exc,
            "aprobacion",
            conflicto=True,
        )

    return Pedido.objects.select_related(
        "proforma",
        "estado",
    ).get(
        proforma=proforma,
    )


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

    if pedido.proforma.vendedor_id != actor.id and not (actor.is_staff or actor.is_superuser):
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

    return pedido
