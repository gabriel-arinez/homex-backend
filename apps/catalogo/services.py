from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from rest_framework.exceptions import ValidationError

from apps.catalogo.models import DescuentoProducto
from apps.media.services import eliminar_objetos, guardar_imagen, url_publica
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
        proforma__estado__codigo="ENVIADA",
    ).aggregate(total=Coalesce(Sum("cantidad"), 0))["total"]


@transaction.atomic
def reemplazar_imagen_principal(*, producto, archivo, actor):
    if not (actor.is_staff or actor.is_superuser):
        raise ValidationError({"producto": "Esta operación requiere administración comercial."})
    key, variantes, dimensiones, _, _ = guardar_imagen(
        archivo,
        prefijo="productos/",
    )
    anterior = producto.imagen_principal.name if producto.imagen_principal else ""
    anterior_variantes = list((producto.imagen_principal_variantes or {}).values())
    producto.imagen_principal.name = key
    producto.imagen_principal_variantes = variantes
    producto.imagen_principal_dimensiones = dimensiones
    producto.updated_by = actor
    try:
        producto.save(
            update_fields=[
                "imagen_principal",
                "imagen_principal_variantes",
                "imagen_principal_dimensiones",
                "updated_by",
            ]
        )
    except Exception:
        eliminar_objetos([key, *variantes.values()])
        raise
    transaction.on_commit(lambda: eliminar_objetos([anterior, *anterior_variantes]))
    return producto


@transaction.atomic
def eliminar_imagen_principal(*, producto, actor):
    if not (actor.is_staff or actor.is_superuser):
        raise ValidationError({"producto": "Esta operación requiere administración comercial."})
    keys = [producto.imagen_principal.name, *(producto.imagen_principal_variantes or {}).values()]
    producto.imagen_principal = None
    producto.imagen_principal_variantes = {}
    producto.imagen_principal_dimensiones = {}
    producto.updated_by = actor
    producto.save(
        update_fields=[
            "imagen_principal",
            "imagen_principal_variantes",
            "imagen_principal_dimensiones",
            "updated_by",
        ]
    )
    transaction.on_commit(lambda: eliminar_objetos(keys))


def imagen_principal_publica(producto):
    if not producto.imagen_principal:
        return None
    dimensiones = producto.imagen_principal_dimensiones or {}
    return {
        "original": url_publica(producto.imagen_principal.name),
        "ancho": dimensiones.get("ancho"),
        "alto": dimensiones.get("alto"),
        "variantes": {
            ancho: url_publica(key) for ancho, key in producto.imagen_principal_variantes.items()
        },
    }
