from django.core.exceptions import ValidationError
from django.db import transaction

from apps.catalog.models import CatalogValue, Product
from apps.inventory.models import StockMovement


@transaction.atomic
def record_initial_stock(
    *, product_id: int, quantity: int, actor_id: int | None = None
) -> StockMovement | None:
    """Registra la única carga inicial permitida para un producto nuevo."""
    if quantity < 0:
        raise ValidationError("La carga inicial no puede ser negativa")
    product = Product.objects.select_for_update().get(pk=product_id)
    if product.stock != 0 or StockMovement.objects.filter(product=product).exists():
        raise ValidationError("El producto ya tiene stock o movimientos registrados")
    if quantity == 0:
        return None

    movement_type = CatalogValue.objects.get(concept__code="TIPO_MOVIMIENTO", code="CARGA_INICIAL")
    product.stock = quantity
    product.save(update_fields=("stock",))
    return StockMovement.objects.create(
        product=product,
        movement_type=movement_type,
        quantity=quantity,
        created_by_id=actor_id,
        observations="Carga inicial desde catálogo confirmado",
    )
