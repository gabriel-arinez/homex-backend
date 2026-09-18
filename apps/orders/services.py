from django.core.exceptions import ValidationError
from django.db import connection, transaction

from apps.catalog.models import CatalogValue, Product
from apps.documents.numbering import next_commercial_number
from apps.inventory.models import StockMovement
from apps.orders.models import Order, OrderTransition
from apps.payments.models import Receipt
from apps.quotations.models import Quotation
from apps.workshop.models import WorkOrder


def value(code: str) -> CatalogValue:
    return CatalogValue.objects.get(code=code)


@transaction.atomic
def approve(quotation_id: int, actor_id: int) -> Order:
    """Aprueba una proforma enviada y registra todos sus efectos comerciales."""
    quotation = Quotation.objects.select_for_update().get(pk=quotation_id)
    if quotation.seller_id != actor_id or quotation.status.code != "ENVIADA":
        raise ValidationError("La proforma no puede aprobarse")

    lines = list(quotation.lines.select_for_update().order_by("pk"))
    products = {
        product.pk: product
        for product in Product.objects.select_for_update()
        .filter(pk__in=[line.product_id for line in lines if line.product_id])
        .order_by("pk")
    }
    for line in lines:
        if line.product_id and products[line.product_id].stock < line.quantity:
            raise ValidationError("Stock insuficiente")

    order = Order.objects.create(
        quotation=quotation,
        status=value("CONFIRMADO"),
        created_by_id=actor_id,
    )
    for line in lines:
        if not line.product_id:
            continue
        product = products[line.product_id]
        if connection.vendor != "postgresql":
            product.stock -= line.quantity
            product.save(update_fields=("stock",))
        StockMovement.objects.create(
            product=product,
            movement_type=value("VENTA"),
            quantity=-line.quantity,
            order=order,
            created_by_id=actor_id,
        )

    WorkOrder.objects.create(
        order=order,
        number=next_commercial_number(sequence_name="seq_ordenes_trabajo_numero", model=WorkOrder),
        status=value("PENDIENTE"),
    )
    quotation.status = value("APROBADA")
    quotation.updated_by_id = actor_id
    quotation.save(update_fields=("status", "updated_by"))
    return order


@transaction.atomic
def transition_order(order_id: int, target_code: str) -> Order:
    """Cambia un pedido sólo mediante una transición configurada explícitamente."""
    order = Order.objects.select_for_update().select_related("status").get(pk=order_id)
    target = value(target_code)
    if not OrderTransition.objects.filter(source=order.status, target=target).exists():
        raise ValidationError("Transición de pedido no permitida")
    order.status = target
    order.save(update_fields=("status",))
    return order


@transaction.atomic
def cancel(order_id: int, actor_id: int) -> Order:
    """Cancela un pedido sin cobros y revierte una sola vez cada venta de stock."""
    order = Order.objects.select_for_update().select_related("status").get(pk=order_id)
    if Receipt.objects.filter(order=order, status=Receipt.Status.ISSUED).exists():
        raise ValidationError("No se puede cancelar un pedido con recibos emitidos")
    if order.status.code not in {"CONFIRMADO", "EN_PRODUCCION", "LISTO_ENTREGA"}:
        raise ValidationError("Pedido no cancelable")

    sales = list(
        StockMovement.objects.select_for_update()
        .filter(order=order, movement_type__code="VENTA")
        .order_by("pk")
    )
    for sale in sales:
        if StockMovement.objects.filter(reference=sale).exists():
            raise ValidationError("Venta ya revertida")
        product = Product.objects.select_for_update().get(pk=sale.product_id)
        if connection.vendor != "postgresql":
            product.stock += -sale.quantity
            product.save(update_fields=("stock",))
        StockMovement.objects.create(
            product=product,
            movement_type=value("REVERSA_VENTA"),
            quantity=-sale.quantity,
            order=order,
            reference=sale,
            created_by_id=actor_id,
        )

    order.status = value("CANCELADO")
    order.save(update_fields=("status",))
    return order
