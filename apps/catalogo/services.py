import re
import unicodedata
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from rest_framework.exceptions import ValidationError

from apps.catalogo.models import DescuentoProducto, Producto
from apps.core.permissions import es_administrador_comercial
from apps.media.services import url_publica
from apps.proformas.models import DetalleProforma

UNIDADES_ENTERAS = frozenset({"PIEZA", "JUEGO", "BARRA", "CAJA"})
ESTADOS_DEMANDA_PENDIENTE = ("EN_REVISION", "ENVIADA")


def validar_cantidad_segun_unidad(
    cantidad: Decimal,
    unidad_codigo: str,
    *,
    permitir_cero: bool = False,
) -> Decimal:
    """Valida signo y granularidad (entera vs decimal M2) según la unidad del producto."""
    if permitir_cero:
        if cantidad < 0:
            raise ValidationError("La cantidad no puede ser negativa.")
    elif cantidad <= 0:
        raise ValidationError("La cantidad debe ser mayor a cero.")

    if unidad_codigo in UNIDADES_ENTERAS and cantidad != cantidad.to_integral_value():
        raise ValidationError(f"La unidad {unidad_codigo} solo admite cantidades enteras.")
    return cantidad


def estado_stock_producto(stock: Decimal, stock_minimo: Decimal | None) -> str:
    """Clasifica el estado físico del stock respecto al umbral mínimo configurado."""
    if stock <= 0:
        return "SIN_EXISTENCIAS"
    if stock_minimo is None:
        return "SIN_MINIMO"
    if stock <= stock_minimo:
        return "STOCK_BAJO"
    return "NORMAL"


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
        proforma__estado__codigo__in=ESTADOS_DEMANDA_PENDIENTE,
    ).aggregate(total=Coalesce(Sum("cantidad"), Decimal("0")))["total"]


def demanda_pendiente_desglose(producto, usuario) -> dict:
    """Desglosa la demanda pendiente del producto respetando el alcance de proformas del usuario."""
    detalles_qs = (
        DetalleProforma.objects.filter(
            producto_id=producto.id,
            proforma__estado__codigo__in=ESTADOS_DEMANDA_PENDIENTE,
        )
        .values(
            "proforma_id",
            "proforma__numero",
            "proforma__fecha",
            "proforma__vendedor_id",
            "proforma__estado__id",
            "proforma__estado__codigo",
            "proforma__estado__nombre",
        )
        .annotate(cantidad=Coalesce(Sum("cantidad"), Decimal("0")))
        .order_by("-proforma__fecha", "-proforma_id")
    )

    es_admin = es_administrador_comercial(usuario)
    total = Decimal("0")
    cantidad_restringida = Decimal("0")
    proformas = []

    for row in detalles_qs:
        cantidad = row["cantidad"] or Decimal("0")
        total += cantidad
        if es_admin or row["proforma__vendedor_id"] == usuario.id:
            proformas.append(
                {
                    "proforma_id": row["proforma_id"],
                    "numero": row["proforma__numero"],
                    "fecha": row["proforma__fecha"],
                    "estado": {
                        "id": row["proforma__estado__id"],
                        "codigo": row["proforma__estado__codigo"],
                        "nombre": row["proforma__estado__nombre"],
                    },
                    "cantidad": str(cantidad),
                }
            )
        else:
            cantidad_restringida += cantidad

    return {
        "producto_id": producto.id,
        "demanda_pendiente_total": str(total),
        "cantidad_restringida": str(cantidad_restringida),
        "proformas": proformas,
    }


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


def _normalizar_texto_catalogo(valor: str | None) -> str:
    if not valor:
        return ""
    sin_tildes = unicodedata.normalize("NFKD", valor).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


def _resumen_similar(producto: Producto, coincidencia: str, motivo: str) -> dict:
    return {
        "id": producto.id,
        "sku": producto.sku,
        "nombre": producto.nombre,
        "categoria_nombre": producto.categoria.nombre,
        "precio_vigente": str(precio_catalogo_vigente(producto)[1]),
        "stock": str(producto.stock),
        "unidad_nombre": producto.unidad_stock.nombre,
        "activo": producto.activo,
        "coincidencia": coincidencia,
        "motivo": motivo,
    }


def buscar_productos_similares(
    *,
    exclude_id: int | None = None,
    sku: str | None = None,
    nombre: str | None = None,
    categoria: int | None = None,
    marca: int | None = None,
    modelo: str | None = None,
    color_primario: int | None = None,
    espesor_mm: Decimal | None = None,
) -> dict:
    base = Producto.objects.select_related(
        "categoria",
        "unidad_stock",
        "productosilla",
        "productopiso",
        "descuentoproducto",
    )
    if exclude_id:
        base = base.exclude(pk=exclude_id)

    sku_duplicado = None
    sku_limpio = (sku or "").strip()
    if sku_limpio:
        exacto_sku = base.filter(sku__iexact=sku_limpio).first()
        if exacto_sku is not None:
            sku_duplicado = _resumen_similar(
                exacto_sku,
                "SKU_EXACTO",
                f"Ya existe el producto con SKU {exacto_sku.sku}.",
            )

    nombre_norm = _normalizar_texto_catalogo(nombre)
    modelo_norm = _normalizar_texto_catalogo(modelo)

    q = Q()
    if len(nombre_norm) >= 3:
        tokens = [tok for tok in nombre_norm.split(" ") if len(tok) >= 3][:4]
        for tok in tokens:
            q |= Q(nombre__icontains=tok)
    if categoria and (marca or len(modelo_norm) >= 2 or color_primario or espesor_mm):
        attr_q = Q(categoria_id=categoria)
        sub_q = Q()
        if marca:
            sub_q |= Q(productosilla__marca_id=marca) | Q(productopiso__marca_id=marca)
        if len(modelo_norm) >= 2:
            sub_q |= Q(productosilla__modelo__icontains=modelo_norm) | Q(
                productopiso__modelo__icontains=modelo_norm
            )
        if color_primario:
            sub_q |= Q(productosilla__color_primario_id=color_primario)
        if espesor_mm is not None:
            sub_q |= Q(productopiso__espesor_mm=espesor_mm)
        if sub_q:
            q |= attr_q & sub_q

    similares_ordenados: list[tuple[int, dict]] = []
    if q:
        candidatos = base.filter(q).distinct()[:50]
        for prod in candidatos:
            if sku_duplicado and prod.id == sku_duplicado["id"]:
                continue
            prod_nombre_norm = _normalizar_texto_catalogo(prod.nombre)
            silla = getattr(prod, "productosilla", None)
            piso = getattr(prod, "productopiso", None)
            prod_marca = silla.marca_id if silla else (piso.marca_id if piso else None)
            prod_modelo = _normalizar_texto_catalogo(
                silla.modelo if silla else (piso.modelo if piso else None)
            )

            nombre_exacto = bool(nombre_norm) and prod_nombre_norm == nombre_norm
            nombre_parecido = (
                len(nombre_norm) >= 4
                and len(prod_nombre_norm) >= 4
                and (nombre_norm in prod_nombre_norm or prod_nombre_norm in nombre_norm)
            )
            misma_categoria = bool(categoria) and prod.categoria_id == categoria
            misma_marca = bool(marca) and prod_marca == marca
            mismo_modelo = bool(modelo_norm) and bool(prod_modelo) and prod_modelo == modelo_norm
            mismo_color = (
                bool(color_primario) and bool(silla) and silla.color_primario_id == color_primario
            )
            mismo_espesor = espesor_mm is not None and bool(piso) and piso.espesor_mm == espesor_mm

            if nombre_exacto:
                similares_ordenados.append(
                    (
                        0,
                        _resumen_similar(prod, "NOMBRE_EXACTO", "Nombre comercial idéntico."),
                    )
                )
            elif misma_categoria and (
                (misma_marca and mismo_modelo)
                or (misma_marca and mismo_color)
                or (misma_marca and mismo_espesor)
            ):
                similares_ordenados.append(
                    (
                        1,
                        _resumen_similar(
                            prod,
                            "ATRIBUTOS_IGUALES",
                            "Coincide en categoría y atributos técnicos clave.",
                        ),
                    )
                )
            elif nombre_parecido or (misma_categoria and mismo_modelo):
                similares_ordenados.append(
                    (
                        2,
                        _resumen_similar(
                            prod,
                            "SIMILAR",
                            "Nombre o modelo muy similar a este registro.",
                        ),
                    )
                )

    similares_ordenados.sort(key=lambda item: (item[0], item[1]["id"]))
    return {
        "sku_duplicado": sku_duplicado,
        "similares": [item[1] for item in similares_ordenados[:5]],
    }
