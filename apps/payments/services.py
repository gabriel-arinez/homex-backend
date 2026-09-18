from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from apps.documents.numbering import next_commercial_number
from apps.orders.models import Order
from apps.payments.models import Receipt


@transaction.atomic
def issue_receipt(
    *,
    order_id: int,
    actor_id: int,
    full_name: str,
    amount_in_words: str,
    concept: str,
    payment_type_id: int,
    current_payment: Decimal,
    check_number: str = "",
    bank: str = "",
) -> Receipt:
    """Registra un cobro sin permitir que los recibos emitidos superen el total."""
    order = Order.objects.select_for_update().select_related("quotation", "status").get(pk=order_id)
    if order.status.code == "CANCELADO":
        raise ValidationError("No se aceptan cobros en pedidos cancelados")
    if current_payment <= 0:
        raise ValidationError("El pago debe ser positivo")

    total = order.quotation.total
    paid = Receipt.objects.select_for_update().filter(
        order=order, status=Receipt.Status.ISSUED
    ).aggregate(value=Sum("current_payment"))["value"] or Decimal("0.00")
    on_account = paid + current_payment
    if on_account > total:
        raise ValidationError("El pago supera el saldo pendiente del pedido")

    return Receipt.objects.create(
        number=next_commercial_number(sequence_name="seq_recibos_numero", model=Receipt),
        order=order,
        full_name=full_name,
        amount_in_words=amount_in_words,
        concept=concept,
        payment_type_id=payment_type_id,
        check_number=check_number,
        bank=bank,
        total=total,
        current_payment=current_payment,
        on_account=on_account,
        balance=total - on_account,
        created_by_id=actor_id,
        updated_by_id=actor_id,
    )


@transaction.atomic
def void_receipt(*, receipt_id: int, actor_id: int) -> Receipt:
    """Anula un recibo erróneo sin borrar ni reescribir su comprobante histórico."""
    receipt = Receipt.objects.select_for_update().select_related("order").get(pk=receipt_id)
    Order.objects.select_for_update().get(pk=receipt.order_id)
    if receipt.status != Receipt.Status.ISSUED:
        raise ValidationError("Sólo se pueden anular recibos emitidos")
    receipt.status = Receipt.Status.VOIDED
    receipt.updated_by_id = actor_id
    receipt.save(update_fields=("status", "updated_by"))
    return receipt
