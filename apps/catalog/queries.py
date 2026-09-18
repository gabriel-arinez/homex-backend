from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.utils.timezone import localdate

from apps.catalog.models import Product, ProductDiscount
from apps.quotations.models import QuotationLine


@dataclass(frozen=True)
class ProductAvailability:
    stock: int
    pending_quotations: int
    reference_availability: int


@dataclass(frozen=True)
class ProductPrice:
    list_price: Decimal
    effective_price: Decimal
    promotion_applied: bool


def pending_quotation_demand(product_id: int) -> int:
    """Unidades en proformas ENVIADA: advertencia, nunca reserva de stock."""
    return (
        QuotationLine.objects.filter(
            product_id=product_id, quotation__status__code="ENVIADA"
        ).aggregate(quantity=Sum("quantity"))["quantity"]
        or 0
    )


def product_availability(product: Product) -> ProductAvailability:
    pending = pending_quotation_demand(product.pk)
    return ProductAvailability(
        stock=product.stock,
        pending_quotations=pending,
        reference_availability=product.stock - pending,
    )


def product_price(product: Product, on_date: date | None = None) -> ProductPrice:
    target_date = on_date or localdate()
    discount = ProductDiscount.objects.filter(product=product, active=True).first()
    if (
        discount
        and (discount.start_date is None or discount.start_date <= target_date)
        and (discount.end_date is None or discount.end_date >= target_date)
    ):
        return ProductPrice(
            list_price=discount.price_before,
            effective_price=discount.price_now,
            promotion_applied=True,
        )
    return ProductPrice(
        list_price=product.list_price,
        effective_price=product.list_price,
        promotion_applied=False,
    )
