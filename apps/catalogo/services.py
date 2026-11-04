from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from rest_framework.exceptions import ValidationError

from apps.catalogo.models import DescuentoProducto
from apps.media.services import url_publica
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


def demanda_pendiente_por_producto(producto_id: int) -> Decimal:
    return DetalleProforma.objects.filter(
        producto_id=producto_id,
        proforma__estado__codigo__in=["EN_REVISION", "ENVIADA"],
    ).aggregate(total=Coalesce(Sum("cantidad"), Decimal("0")))["total"]


@transaction.atomic
def reemplazar_imagen_principal(*, producto, archivo, actor):
    from apps.catalogo.models import ImagenProducto, Producto
    from apps.core.permissions import puede_crear_producto
    from apps.media.gallery import sincronizar_portada, subir

    if not puede_crear_producto(actor):
        raise ValidationError({"producto": "Se requiere permiso comercial."})
    producto = Producto.objects.select_for_update().get(pk=producto.pk)
    anterior = producto.imagenes.filter(principal=True).first()

    # Validate/store before removing the existing cover. Any DB failure rolls back removals.
    def crear(**kw):
        kw.pop("mime")
        kw.pop("size")
        if anterior:
            anterior.delete()
        kw["principal"] = True
        return ImagenProducto.objects.create(producto=producto, **kw)

    subir(
        producto.imagenes.exclude(pk=anterior.pk) if anterior else producto.imagenes.all(),
        archivo,
        crear,
    )
    sincronizar_portada(producto)
    return producto


@transaction.atomic
def eliminar_imagen_principal(*, producto, actor):
    from apps.catalogo.models import Producto
    from apps.core.permissions import puede_crear_producto
    from apps.media.gallery import modificar, sincronizar_portada

    if not puede_crear_producto(actor):
        raise ValidationError({"producto": "Se requiere permiso comercial."})
    producto = Producto.objects.select_for_update().get(pk=producto.pk)
    anterior = producto.imagenes.filter(principal=True).first()
    if anterior:
        modificar(producto.imagenes.all(), {"eliminar": anterior.pk})
    sincronizar_portada(producto)


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
