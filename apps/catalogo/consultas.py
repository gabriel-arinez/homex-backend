from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.utils.timezone import localdate

from apps.catalogo.models import DescuentoProducto, Producto
from apps.proformas.models import DetalleProforma


@dataclass(frozen=True)
class ProductoAvailability:
    stock: int
    pending_quotations: int
    reference_availability: int


@dataclass(frozen=True)
class ProductoPrice:
    precio_lista: Decimal
    effective_price: Decimal
    promotion_applied: bool


def demanda_proformas_pendientes(producto_id: int) -> int:
    """Unidades en proformas ENVIADA: advertencia, nunca reserva de stock."""
    return (
        DetalleProforma.objects.filter(
            producto_id=producto_id, proforma__estado__codigo="ENVIADA"
        ).aggregate(cantidad=Sum("cantidad"))["cantidad"]
        or 0
    )


def disponibilidad_producto(producto: Producto) -> ProductoAvailability:
    pending = demanda_proformas_pendientes(producto.pk)
    return ProductoAvailability(
        stock=producto.stock,
        pending_quotations=pending,
        reference_availability=producto.stock - pending,
    )


def precio_producto(producto: Producto, on_date: date | None = None) -> ProductoPrice:
    destino_date = on_date or localdate()
    descuento = DescuentoProducto.objects.filter(producto=producto, activo=True).first()
    if (
        descuento
        and (descuento.fecha_inicio is None or descuento.fecha_inicio <= destino_date)
        and (descuento.fecha_fin is None or descuento.fecha_fin >= destino_date)
    ):
        return ProductoPrice(
            precio_lista=descuento.precio_antes,
            effective_price=descuento.precio_ahora,
            promotion_applied=True,
        )
    return ProductoPrice(
        precio_lista=producto.precio_lista,
        effective_price=producto.precio_lista,
        promotion_applied=False,
    )
