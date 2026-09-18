from django.template.loader import render_to_string

from apps.deliveries.models import DeliveryNote
from apps.payments.models import Receipt
from apps.quotations.models import Quotation
from apps.workshop.models import WorkOrder


def _quotation_context(quotation: Quotation) -> dict:
    return {
        "quotation": quotation,
        "customer_name": quotation.customer_name_snapshot,
        "customer_company": quotation.customer_company_snapshot,
        "customer_phone": quotation.customer_phone_snapshot,
        "customer_address": quotation.customer_address_snapshot,
        "lines": quotation.lines.all().order_by("pk"),
    }


def render_quotation(quotation_id: int) -> str:
    quotation = Quotation.objects.prefetch_related("lines").get(pk=quotation_id)
    return render_to_string("documents/quotation.html", _quotation_context(quotation))


def render_work_order(work_order_id: int) -> str:
    work_order = (
        WorkOrder.objects.select_related("order__quotation")
        .prefetch_related("order__quotation__lines")
        .get(pk=work_order_id)
    )
    context = _quotation_context(work_order.order.quotation) | {"work_order": work_order}
    return render_to_string("documents/work_order.html", context)


def render_delivery_note(delivery_note_id: int) -> str:
    delivery_note = (
        DeliveryNote.objects.select_related("order__quotation", "seller")
        .prefetch_related("order__quotation__lines")
        .get(pk=delivery_note_id)
    )
    context = _quotation_context(delivery_note.order.quotation) | {"delivery_note": delivery_note}
    return render_to_string("documents/delivery_note.html", context)


def render_receipt(receipt_id: int) -> str:
    receipt = Receipt.objects.select_related("order__quotation", "payment_type").get(pk=receipt_id)
    return render_to_string("documents/receipt.html", {"receipt": receipt})
