from django.db import DatabaseError, connection, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core.db_errors import traducir_error_comercial_postgresql
from apps.recibos.models import Recibo


def _numero():
    with connection.cursor() as c:
        c.execute("SELECT nextval('seq_recibos_numero')")
        return c.fetchone()[0]


def _autorizar_pedido(*, pedido, actor):
    if actor.is_staff or actor.is_superuser:
        return

    if pedido.proforma.vendedor_id != actor.id:
        raise PermissionDenied("El pedido no pertenece al vendedor autenticado.")


@transaction.atomic
def emitir_recibo(*, pedido, actor, **datos):
    pedido = pedido.__class__.objects.select_related("proforma").get(pk=pedido.pk)

    _autorizar_pedido(
        pedido=pedido,
        actor=actor,
    )

    try:
        recibo = Recibo.objects.create(
            numero=_numero(),
            pedido=pedido,
            fecha=timezone.localdate(),
            created_by=actor,
            updated_by=actor,
            **datos,
        )
    except DatabaseError as exc:
        traducir_error_comercial_postgresql(
            exc,
            "recibo",
        )

    # PostgreSQL calcula total, acumulado y saldo.
    recibo.refresh_from_db()

    return recibo


@transaction.atomic
def anular_recibo(*, recibo_id, actor):
    recibo = Recibo.objects.select_related("pedido__proforma").select_for_update().get(pk=recibo_id)

    _autorizar_pedido(
        pedido=recibo.pedido,
        actor=actor,
    )

    if recibo.estado != "EMITIDO":
        raise ValidationError(
            {
                "estado": "El recibo ya está anulado.",
            }
        )

    recibo.estado = "ANULADO"
    recibo.updated_by = actor

    try:
        recibo.save(
            update_fields=[
                "estado",
                "updated_by",
            ]
        )
    except DatabaseError as exc:
        traducir_error_comercial_postgresql(
            exc,
            "anulacion",
        )

    return recibo
