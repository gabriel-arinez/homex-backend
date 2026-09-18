import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from apps.catalogo.models import Producto, ProductoSilla, ValorCatalogo
from apps.movimientos_stock.models import MovimientoStock
from apps.movimientos_stock.servicios import registrar_carga_inicial


@dataclass
class ImportReport:
    created: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors


def _catalog_value(concepto_codigo: str, value_codigo: str | None) -> ValorCatalogo | None:
    if value_codigo in (None, ""):
        return None
    try:
        return ValorCatalogo.objects.get(concepto__codigo=concepto_codigo, codigo=value_codigo)
    except ValorCatalogo.DoesNotExist as error:
        raise ValidationError(f"No existe {concepto_codigo}:{value_codigo}") from error


def _read_rows(input_path: Path) -> list[dict]:
    raw_content = input_path.read_text(encoding="utf-8").strip()
    try:
        content = json.loads(raw_content)
    except json.JSONDecodeError:
        rows = []
        for detalle_numero, detalle in enumerate(raw_content.splitdetalles(), start=1):
            if not detalle.strip():
                continue
            try:
                rows.append(json.loads(detalle))
            except json.JSONDecodeError as error:
                raise ValidationError(f"JSON inválido en línea {detalle_numero}") from error
        return rows
    if not isinstance(content, list):
        raise ValidationError("El archivo debe ser un arreglo JSON o JSONL")
    return content


def _normalize_row(row: dict, row_numero: int) -> dict:
    required = ("sku", "nombre", "precio_lista", "stock")
    if not isinstance(row, dict):
        raise ValidationError(f"Fila {row_numero}: se esperaba un objeto JSON")
    missing = [nombre for nombre in required if row.get(nombre) in (None, "")]
    if missing:
        raise ValidationError(f"Fila {row_numero}: faltan {', '.join(missing)}")
    try:
        price = Decimal(str(row["precio_lista"]))
        stock = int(row["stock"])
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValidationError(f"Fila {row_numero}: precio o stock inválido") from error
    if price < 0 or stock < 0:
        raise ValidationError(f"Fila {row_numero}: precio y stock deben ser no negativos")
    especificaciones = row.get("especificaciones")
    if especificaciones is not None and not isinstance(especificaciones, dict):
        raise ValidationError(f"Fila {row_numero}: especificaciones debe ser un objeto")
    if row.get("color_secundario_codigo") and not row.get("color_primario_codigo"):
        raise ValidationError(f"Fila {row_numero}: color secundario requiere color primario")
    return {
        "sku": str(row["sku"]).strip(),
        "nombre": str(row["nombre"]).strip(),
        "precio_lista": price,
        "stock": stock,
        "marca_codigo": row.get("marca_codigo"),
        "modelo": str(row.get("modelo", "")).strip(),
        "color_primario_codigo": row.get("color_primario_codigo"),
        "color_secundario_codigo": row.get("color_secundario_codigo"),
        "especificaciones": especificaciones,
        "observaciones": str(row.get("observaciones", "")).strip(),
    }


def _matches(producto: Producto, silla: ProductoSilla, row: dict, valores: dict) -> bool:
    return (
        producto.nombre == row["nombre"]
        and producto.precio_lista == row["precio_lista"]
        and producto.categoria_id == valores["categoria"].pk
        and producto.unidad_stock_id == valores["unidad"].pk
        and producto.observaciones == row["observaciones"]
        and silla.marca_id == (valores["marca"].pk if valores["marca"] else None)
        and silla.modelo == row["modelo"]
        and silla.color_primario_id
        == (valores["color_primario"].pk if valores["color_primario"] else None)
        and silla.color_secundario_id
        == (valores["color_secundario"].pk if valores["color_secundario"] else None)
        and silla.especificaciones == row["especificaciones"]
    )


@transaction.atomic
def importar_sillas(
    *, input_path: Path, dry_run: bool, actor_id: int | None = None
) -> ImportReport:
    """Importa sólo fichas comerciales completas y no altera un SKU existente."""
    report = ImportReport()
    try:
        rows = _read_rows(input_path)
    except ValidationError as error:
        report.errors.append(str(error))
        return report

    seen_skus: set[str] = set()
    normalized_rows: list[dict] = []
    for index, raw_row in enumerate(rows, start=1):
        try:
            row = _normalize_row(raw_row, index)
            if not row["sku"]:
                raise ValidationError(f"Fila {index}: SKU vacío")
            if row["sku"] in seen_skus:
                raise ValidationError(f"Fila {index}: SKU duplicado en el archivo: {row['sku']}")
            seen_skus.add(row["sku"])
            normalized_rows.append(row)
        except ValidationError as error:
            report.errors.append(str(error))

    if report.errors:
        transaction.set_rollback(True)
        return report

    try:
        categoria = _catalog_value("CATEGORIA_PRODUCTO", "SILLA")
        unidad = _catalog_value("UNIDAD_MEDIDA", "PIEZA")
        _catalog_value("TIPO_MOVIMIENTO", "CARGA_INICIAL")
    except ValidationError as error:
        report.errors.append(str(error))
        transaction.set_rollback(True)
        return report

    resolved_rows: list[tuple[dict, dict]] = []
    for row in normalized_rows:
        try:
            resolved_rows.append(
                (
                    row,
                    {
                        "categoria": categoria,
                        "unidad": unidad,
                        "marca": _catalog_value("MARCA", row["marca_codigo"]),
                        "color_primario": _catalog_value("COLOR", row["color_primario_codigo"]),
                        "color_secundario": _catalog_value("COLOR", row["color_secundario_codigo"]),
                    },
                )
            )
        except ValidationError as error:
            report.errors.append(f"SKU {row['sku']}: {error}")

    if report.errors:
        transaction.set_rollback(True)
        return report

    for row, valores in resolved_rows:
        try:
            producto = Producto.objects.select_for_update().get(sku=row["sku"])
        except Producto.DoesNotExist:
            producto = Producto.objects.create(
                sku=row["sku"],
                nombre=row["nombre"],
                precio_lista=row["precio_lista"],
                stock=0,
                unidad_stock=valores["unidad"],
                categoria=valores["categoria"],
                observaciones=row["observaciones"],
                creado_por_id=actor_id,
                actualizado_por_id=actor_id,
            )
            ProductoSilla.objects.create(
                producto=producto,
                marca=valores["marca"],
                modelo=row["modelo"],
                color_primario=valores["color_primario"],
                color_secundario=valores["color_secundario"],
                especificaciones=row["especificaciones"],
                creado_por_id=actor_id,
                actualizado_por_id=actor_id,
            )
            registrar_carga_inicial(producto_id=producto.pk, cantidad=row["stock"], actor_id=actor_id)
            report.created += 1
            continue

        try:
            silla = producto.silla
        except ProductoSilla.DoesNotExist:
            report.errors.append(f"SKU {row['sku']}: existe, pero no es una silla")
            continue
        initial_stock = MovimientoStock.objects.filter(
            producto=producto, tipo_movimiento__codigo="CARGA_INICIAL"
        ).aggregate(total=Sum("cantidad"))["total"]
        if not _matches(producto, silla, row, valores) or initial_stock != row["stock"]:
            report.errors.append(f"SKU {row['sku']}: difiere de la ficha ya importada")
            continue
        report.skipped += 1

    if report.errors or dry_run:
        transaction.set_rollback(True)
    return report
