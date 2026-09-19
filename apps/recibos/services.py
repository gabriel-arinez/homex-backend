from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.recibos.models import Recibo


def _numero():
    with connection.cursor() as c:
        c.execute("SELECT nextval('seq_recibos_numero')")
        return c.fetchone()[0]


@transaction.atomic
def emitir_recibo(*, pedido, actor, **datos):
    recibo = Recibo.objects.create(
        numero=_numero(),
        pedido=pedido,
        fecha=timezone.localdate(),
        created_by=actor,
        updated_by=actor,
        **datos,
    )
    # PostgreSQL calcula estos campos en el trigger BEFORE INSERT.
    recibo.refresh_from_db()
    return recibo


@transaction.atomic
def anular_recibo(*, recibo_id, actor):
    recibo = Recibo.objects.select_for_update().get(pk=recibo_id)
    if recibo.estado != "EMITIDO":
        raise ValidationError({"estado": "El recibo ya está anulado."})
    recibo.estado = "ANULADO"
    recibo.updated_by = actor
    recibo.save(update_fields=["estado", "updated_by"])
    return recibo
