from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce

from apps.catalogo.models import DescuentoProducto
from apps.proformas.models import DetalleProforma


def descuento_vigente(producto, hoy: date | None = None) -> DescuentoProducto | None:
    hoy = hoy or date.today()
    try:
        descuento = producto.descuentoproducto
    except DescuentoProducto.DoesNotExist:
        return None
    if not descuento.activo:
        return None
    if descuento.fecha_inicio and descuento.fecha_inicio > hoy:
        return None
    if descuento.fecha_fin and descuento.fecha_fin < hoy:
        return None
    return descuento


def precio_catalogo_vigente(producto, hoy: date | None = None) -> tuple[Decimal, Decimal, Decimal]:
    """Devuelve precio base, precio aplicable y descuento por unidad en BOB."""
    descuento = descuento_vigente(producto, hoy)
    if descuento is None:
        return producto.precio_lista, producto.precio_lista, Decimal("0.00")
    return (
        descuento.precio_antes,
        descuento.precio_ahora,
        descuento.precio_antes - descuento.precio_ahora,
    )


def demanda_pendiente_por_producto(producto_id: int) -> int:
    return DetalleProforma.objects.filter(
        producto_id=producto_id,
        proforma__estado__codigo__in=["BORRADOR", "ENVIADA"],
    ).aggregate(total=Coalesce(Sum("cantidad"), 0))["total"]
