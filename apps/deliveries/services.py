from django.core.exceptions import ValidationError
from django.db import transaction

from apps.deliveries.models import DeliveryNote
from apps.documents.numbering import next_commercial_number
from apps.orders.models import Order


@transaction.atomic
def issue_delivery_note(*, order_id: int, seller_id: int, actor_id: int) -> DeliveryNote:
    """Emite la única nota de entrega cuando el pedido está listo para entregar."""
    order = Order.objects.select_for_update().select_related("status").get(pk=order_id)
    if order.status.code != "LISTO_ENTREGA":
        raise ValidationError("La nota sólo puede emitirse para un pedido listo para entrega")
    if DeliveryNote.objects.filter(order=order).exists():
        raise ValidationError("El pedido ya tiene una nota de entrega")
    return DeliveryNote.objects.create(
        order=order,
        seller_id=seller_id,
        number=next_commercial_number(sequence_name="seq_notas_entrega_numero", model=DeliveryNote),
        created_by_id=actor_id,
        updated_by_id=actor_id,
    )
