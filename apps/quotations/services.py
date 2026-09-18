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


def submit_quotation(quotation_id: int, actor_id: int) -> Quotation:
    quotation = (
        Quotation.objects.select_for_update().select_related("customer").get(pk=quotation_id)
    )
    if quotation.seller_id != actor_id:
        raise ValidationError("Solo el vendedor responsable puede enviar la proforma")
    if quotation.customer_id is None:
        raise ValidationError("Una proforma enviada requiere cliente registrado")
    if quotation.status.code != "BORRADOR":
        raise ValidationError("Solo un borrador puede enviarse")
    customer = quotation.customer
    quotation.customer_name_snapshot = " ".join(
        filter(None, (customer.first_names, customer.last_names))
    )
    quotation.customer_company_snapshot = customer.company
    quotation.customer_phone_snapshot = customer.phone
    quotation.customer_address_snapshot = customer.address
    quotation.status = quotation.status.__class__.objects.get(code="ENVIADA")
    quotation.updated_by_id = actor_id
    quotation.save()
    return quotation


def update_draft(quotation_id: int, actor_id: int, **changes) -> Quotation:
    quotation = Quotation.objects.select_for_update().get(pk=quotation_id)
    if quotation.seller_id != actor_id or quotation.status.code != "BORRADOR":
        raise ValidationError("Solo el vendedor puede editar su borrador")
    protected = {
        "subtotal",
        "discount_total",
        "total",
        "customer_name_snapshot",
        "customer_company_snapshot",
        "customer_phone_snapshot",
        "customer_address_snapshot",
    }
    if protected.intersection(changes):
        raise ValidationError("Los totales y snapshots no se editan directamente")
    for field, value in changes.items():
        setattr(quotation, field, value)
    quotation.updated_by_id = actor_id
    quotation.save()
    return quotation
