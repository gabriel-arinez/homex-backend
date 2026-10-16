"""Huella de revisión de datos comerciales del producto (sin cambios de stock)."""

import hashlib
import json

from apps.catalogo.models import DescuentoProducto, Producto, ProductoPiso, ProductoSilla


def _ficha(producto, nombre, modelo, campos):
    try:
        ficha = getattr(producto, nombre)
    except modelo.DoesNotExist:
        return None
    return {campo: getattr(ficha, campo) for campo in campos}


def revision_producto(producto: Producto) -> str:
    campos = (
        "id", "categoria_id", "familia_id", "sku", "nombre",
        "precio_lista", "unidad_stock_id", "activo", "observaciones",
        "imagen_principal",
    )
    datos = {campo: str(getattr(producto, campo)) for campo in campos}
    datos["silla"] = _ficha(
        producto, "productosilla", ProductoSilla,
        ("marca_id", "modelo", "color_primario_id", "color_secundario_id", "especificaciones"),
    )
    datos["piso"] = _ficha(
        producto, "productopiso", ProductoPiso,
        ("marca_id", "modelo", "tipo_id", "material_id", "diseno_id", "acabado_id",
         "espesor_mm", "largo_mm", "ancho_mm", "m2_por_caja"),
    )
    datos["promocion"] = _ficha(
        producto, "descuentoproducto", DescuentoProducto,
        ("precio_antes", "precio_ahora", "fecha_inicio", "fecha_fin", "activo"),
    )
    payload = json.dumps(datos, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
