from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.quotations.models import Quotation, QuotationLine


def recalculate_line(line: QuotationLine) -> QuotationLine:
    if line.calculation_mode == QuotationLine.CalculationMode.NEGOTIATED:
        if line.negotiated_amount is None:
            raise ValidationError("TOTAL_NEGOCIADO requiere importe negociado")
        line.total = line.negotiated_amount
    else:
        line.total = line.quantity * line.unit_price - line.discount
    if line.total < Decimal(0):
        raise ValidationError("El total de línea no puede ser negativo")
    return line


@transaction.atomic
def recalculate_quotation(quotation_id: int) -> Quotation:
    quotation = Quotation.objects.select_for_update().get(pk=quotation_id)
    subtotal = Decimal(0)
    discount = Decimal(0)
    for line in quotation.lines.select_for_update():
        recalculate_line(line)
        line.save(update_fields=("total",))
        subtotal += line.total
        discount += line.discount
    quotation.subtotal, quotation.discount_total, quotation.total = (
        subtotal + discount,
        discount,
        subtotal,
    )
    quotation.save(update_fields=("subtotal", "discount_total", "total"))
    return quotation
