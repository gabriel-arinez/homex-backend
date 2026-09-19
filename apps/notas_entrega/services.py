from django.db import DatabaseError, connection, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.core.db_errors import traducir_error_comercial_postgresql
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
def emitir_nota(*, pedido, actor):
    pedido = pedido.__class__.objects.select_related("proforma").get(pk=pedido.pk)

    _autorizar_pedido(
        pedido=pedido,
        actor=actor,
    )

    try:
        return NotaEntrega.objects.create(
            pedido=pedido,
            vendedor=actor,
            numero=_numero(),
            fecha=timezone.localdate(),
            created_by=actor,
            updated_by=actor,
        )
    except DatabaseError as exc:
        traducir_error_comercial_postgresql(
            exc,
            "nota_entrega",
        )
