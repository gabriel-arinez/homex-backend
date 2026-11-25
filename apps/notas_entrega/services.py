from django.db import DatabaseError, connection, transaction
from rest_framework.exceptions import PermissionDenied

from apps.core.db_errors import traducir_error_comercial_postgresql
from apps.core.tiempo_comercial import fecha_comercial_actual, fecha_hora_comercial_actual
from apps.notas_entrega.models import NotaEntrega


def _numero():
    with connection.cursor() as c:
        c.execute("SELECT nextval('seq_notas_entrega_numero')")
        return c.fetchone()[0]


def _autorizar_pedido(*, pedido, actor):
    if actor.is_staff or actor.is_superuser:
        return

    if pedido.proforma.vendedor_id != actor.id:
        raise PermissionDenied("El pedido no pertenece al vendedor autenticado.")


@transaction.atomic
def emitir_nota(*, pedido, actor, permitir_taller: bool = False):
    pedido = pedido.__class__.objects.select_related("proforma").get(pk=pedido.pk)

    if not (permitir_taller and not (actor.is_staff or actor.is_superuser)):
        _autorizar_pedido(
            pedido=pedido,
            actor=actor,
        )

    vendedor_responsable = pedido.proforma.vendedor if permitir_taller else actor

    try:
        return NotaEntrega.objects.create(
            pedido=pedido,
            vendedor=vendedor_responsable,
            numero=_numero(),
            fecha=fecha_comercial_actual(),
            fecha_hora=fecha_hora_comercial_actual(),
            created_by=actor,
            updated_by=actor,
        )
    except DatabaseError as exc:
        traducir_error_comercial_postgresql(
            exc,
            "nota_entrega",
        )
