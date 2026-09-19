import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from apps.catalogo.models import Producto, ProductoPiso, ProductoSilla, ValorCatalogo
from apps.movimientos_stock.models import MovimientoStock


class ErrorCatalogo(ValueError):
    pass


@dataclass(frozen=True)
class ResultadoImportacion:
    creados: int
    existentes: int
    movimientos_stock: int


def cargar_archivo_catalogo(ruta: str | Path) -> dict:
    try:
        contenido = Path(ruta).read_text(encoding="utf-8")
        datos = json.loads(contenido)
    except (OSError, json.JSONDecodeError) as exc:
        raise ErrorCatalogo(
            "El catálogo debe ser un archivo JSON comercial válido; JSONL NER no es aceptado."
        ) from exc
    if (
        not isinstance(datos, dict)
        or datos.get("schema_version") != 1
        or not isinstance(datos.get("productos"), list)
    ):
        raise ErrorCatalogo(
            "Se requiere JSON comercial schema_version=1; JSONL NER no es un catálogo válido."
        )
    return datos


def _valor(concepto: str, codigo: str) -> ValorCatalogo:
    try:
        return ValorCatalogo.objects.get(concepto__codigo=concepto, codigo=codigo, activo=True)
    except ValorCatalogo.DoesNotExist as exc:
        raise ErrorCatalogo(f"No existe un valor activo {concepto}.{codigo}.") from exc


def _decimal(valor, campo: str) -> Decimal:
    try:
        resultado = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ErrorCatalogo(f"{campo} debe ser un decimal válido.") from exc
    if resultado < 0:
        raise ErrorCatalogo(f"{campo} no puede ser negativo.")
    return resultado


def _requerir(item: dict, campo: str):
    valor = item.get(campo)
    if valor in (None, ""):
        raise ErrorCatalogo(f"Cada producto requiere {campo}.")
    return valor


def _validar_lote(productos: list[dict]) -> None:
    skus = []
    for item in productos:
        if not isinstance(item, dict):
            raise ErrorCatalogo("Cada producto debe ser un objeto JSON.")
        sku = _requerir(item, "sku")
        _requerir(item, "categoria")
        _requerir(item, "nombre")
        _requerir(item, "unidad_stock")
        _requerir(item, "precio_lista")
        _requerir(item, "stock_inicial")
        skus.append(sku)
    if len(skus) != len(set(skus)):
        raise ErrorCatalogo("El archivo contiene SKU duplicados.")


@transaction.atomic
def importar_catalogo(*, datos: dict, actor, dry_run: bool = False) -> ResultadoImportacion:
    if not isinstance(datos, dict) or datos.get("schema_version") != 1:
        raise ErrorCatalogo("schema_version=1 es obligatorio.")
    productos = datos.get("productos")
    if not isinstance(productos, list):
        raise ErrorCatalogo("productos debe ser una lista.")
    _validar_lote(productos)
    creados = existentes = movimientos = 0
    for item in productos:
        sku = item["sku"]
        categoria = _valor("CATEGORIA_PRODUCTO", item["categoria"])
        unidad = _valor("UNIDAD_MEDIDA", item["unidad_stock"])
        precio = _decimal(item["precio_lista"], "precio_lista")
        stock = _decimal(item["stock_inicial"], "stock_inicial")
        if stock != stock.to_integral_value():
            raise ErrorCatalogo("stock_inicial debe ser entero.")
        producto = Producto.objects.filter(sku=sku).first()
        if producto:
            if producto.categoria_id != categoria.id or producto.unidad_stock_id != unidad.id:
                raise ErrorCatalogo(f"SKU {sku} ya existe con una clasificación distinta.")
            existentes += 1
            continue
        producto = Producto.objects.create(
            categoria=categoria,
            sku=sku,
            nombre=item["nombre"],
            precio_lista=precio,
            stock=0,
            unidad_stock=unidad,
            activo=item.get("activo", True),
            observaciones=item.get("observaciones"),
            created_by=actor,
            updated_by=actor,
        )
        ficha = item.get("ficha")
        if categoria.codigo == "SILLA":
            if not isinstance(ficha, dict):
                raise ErrorCatalogo(f"SKU {sku} requiere ficha de silla.")
            ProductoSilla.objects.create(
                producto=producto,
                marca=_valor("MARCA", ficha["marca"]) if ficha.get("marca") else None,
                modelo=ficha.get("modelo"),
                color_primario=_valor("COLOR", ficha["color_primario"])
                if ficha.get("color_primario")
                else None,
                color_secundario=_valor("COLOR", ficha["color_secundario"])
                if ficha.get("color_secundario")
                else None,
                especificaciones=ficha.get("especificaciones"),
                created_by=actor,
                updated_by=actor,
            )
        elif categoria.codigo == "PISO_FLOTANTE":
            if not isinstance(ficha, dict):
                raise ErrorCatalogo(f"SKU {sku} requiere ficha de piso.")
            ProductoPiso.objects.create(
                producto=producto, modelo=ficha.get("modelo"), created_by=actor, updated_by=actor
            )
        if stock:
            MovimientoStock.objects.create(
                producto=producto,
                fecha=timezone.now(),
                tipo_movimiento=_valor("TIPO_MOVIMIENTO", "CARGA_INICIAL"),
                cantidad=int(stock),
                observaciones="Carga inicial por importación de catálogo",
                created_by=actor,
            )
            movimientos += 1
        creados += 1
    resultado = ResultadoImportacion(creados, existentes, movimientos)
    if dry_run:
        transaction.set_rollback(True)
    return resultado
