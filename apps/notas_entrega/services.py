from django.db import connection, transaction
from django.utils import timezone

from apps.notas_entrega.models import NotaEntrega


def _numero():
    with connection.cursor() as c:
        c.execute("SELECT nextval('seq_notas_entrega_numero')")
        return c.fetchone()[0]


@transaction.atomic
def emitir_nota(*, pedido, actor):
    return NotaEntrega.objects.create(
        pedido=pedido,
        vendedor=actor,
        numero=_numero(),
        fecha=timezone.localdate(),
        created_by=actor,
        updated_by=actor,
    )
