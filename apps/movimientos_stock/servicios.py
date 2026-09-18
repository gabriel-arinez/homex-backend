from django.core.exceptions import ValidationError
from django.db import connection, transaction

from apps.catalogo.models import Producto, ValorCatalogo
from apps.movimientos_stock.models import MovimientoStock


@transaction.atomic
def registrar_carga_inicial(
    *, producto_id: int, cantidad: int, actor_id: int | None = None
) -> MovimientoStock | None:
    """Registra la única carga inicial permitida para un producto nuevo."""
    if cantidad < 0:
        raise ValidationError("La carga inicial no puede ser negativa")
    producto = Producto.objects.select_for_update().get(pk=producto_id)
    if producto.stock != 0 or MovimientoStock.objects.filter(producto=producto).exists():
        raise ValidationError("El producto ya tiene stock o movimientos registrados")
    if cantidad == 0:
        return None

    tipo_movimiento = ValorCatalogo.objects.get(concepto__codigo="TIPO_MOVIMIENTO", codigo="CARGA_INICIAL")
    if connection.vendor != "postgresql":
        producto.stock = cantidad
        producto.save(update_fields=("stock",))
    return MovimientoStock.objects.create(
        producto=producto,
        tipo_movimiento=tipo_movimiento,
        cantidad=cantidad,
        creado_por_id=actor_id,
        observaciones="Carga inicial desde catálogo confirmado",
    )
