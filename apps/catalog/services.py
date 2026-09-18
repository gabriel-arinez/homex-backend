import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from apps.catalog.models import CatalogValue, ChairProduct, Product
from apps.inventory.models import StockMovement
from apps.inventory.services import record_initial_stock


@dataclass
class ImportReport:
    created: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors


def _catalog_value(concept_code: str, value_code: str | None) -> CatalogValue | None:
    if value_code in (None, ""):
        return None
    try:
        return CatalogValue.objects.get(concept__code=concept_code, code=value_code)
    except CatalogValue.DoesNotExist as error:
        raise ValidationError(f"No existe {concept_code}:{value_code}") from error


def _read_rows(input_path: Path) -> list[dict]:
    raw_content = input_path.read_text(encoding="utf-8").strip()
    try:
        content = json.loads(raw_content)
    except json.JSONDecodeError:
        rows = []
        for line_number, line in enumerate(raw_content.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValidationError(f"JSON inválido en línea {line_number}") from error
        return rows
    if not isinstance(content, list):
        raise ValidationError("El archivo debe ser un arreglo JSON o JSONL")
    return content


def _normalize_row(row: dict, row_number: int) -> dict:
    required = ("sku", "name", "list_price", "stock")
    if not isinstance(row, dict):
        raise ValidationError(f"Fila {row_number}: se esperaba un objeto JSON")
    missing = [name for name in required if row.get(name) in (None, "")]
    if missing:
        raise ValidationError(f"Fila {row_number}: faltan {', '.join(missing)}")
    try:
        price = Decimal(str(row["list_price"]))
        stock = int(row["stock"])
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValidationError(f"Fila {row_number}: precio o stock inválido") from error
    if price < 0 or stock < 0:
        raise ValidationError(f"Fila {row_number}: precio y stock deben ser no negativos")
    specifications = row.get("specifications")
    if specifications is not None and not isinstance(specifications, dict):
        raise ValidationError(f"Fila {row_number}: specifications debe ser un objeto")
    if row.get("secondary_color_code") and not row.get("primary_color_code"):
        raise ValidationError(f"Fila {row_number}: color secundario requiere color primario")
    return {
        "sku": str(row["sku"]).strip(),
        "name": str(row["name"]).strip(),
        "list_price": price,
        "stock": stock,
        "brand_code": row.get("brand_code"),
        "model": str(row.get("model", "")).strip(),
        "primary_color_code": row.get("primary_color_code"),
        "secondary_color_code": row.get("secondary_color_code"),
        "specifications": specifications,
        "observations": str(row.get("observations", "")).strip(),
    }


def _matches(product: Product, chair: ChairProduct, row: dict, values: dict) -> bool:
    return (
        product.name == row["name"]
        and product.list_price == row["list_price"]
        and product.category_id == values["category"].pk
        and product.stock_unit_id == values["unit"].pk
        and product.observations == row["observations"]
        and chair.brand_id == (values["brand"].pk if values["brand"] else None)
        and chair.model == row["model"]
        and chair.primary_color_id
        == (values["primary_color"].pk if values["primary_color"] else None)
        and chair.secondary_color_id
        == (values["secondary_color"].pk if values["secondary_color"] else None)
        and chair.specifications == row["specifications"]
    )


@transaction.atomic
def import_chairs(*, input_path: Path, dry_run: bool, actor_id: int | None = None) -> ImportReport:
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
        category = _catalog_value("CATEGORIA_PRODUCTO", "SILLA")
        unit = _catalog_value("UNIDAD_MEDIDA", "PIEZA")
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
                        "category": category,
                        "unit": unit,
                        "brand": _catalog_value("MARCA", row["brand_code"]),
                        "primary_color": _catalog_value("COLOR", row["primary_color_code"]),
                        "secondary_color": _catalog_value("COLOR", row["secondary_color_code"]),
                    },
                )
            )
        except ValidationError as error:
            report.errors.append(f"SKU {row['sku']}: {error}")

    if report.errors:
        transaction.set_rollback(True)
        return report

    for row, values in resolved_rows:
        try:
            product = Product.objects.select_for_update().get(sku=row["sku"])
        except Product.DoesNotExist:
            product = Product.objects.create(
                sku=row["sku"],
                name=row["name"],
                list_price=row["list_price"],
                stock=0,
                stock_unit=values["unit"],
                category=values["category"],
                observations=row["observations"],
                created_by_id=actor_id,
                updated_by_id=actor_id,
            )
            ChairProduct.objects.create(
                product=product,
                brand=values["brand"],
                model=row["model"],
                primary_color=values["primary_color"],
                secondary_color=values["secondary_color"],
                specifications=row["specifications"],
                created_by_id=actor_id,
                updated_by_id=actor_id,
            )
            record_initial_stock(product_id=product.pk, quantity=row["stock"], actor_id=actor_id)
            report.created += 1
            continue

        try:
            chair = product.chair
        except ChairProduct.DoesNotExist:
            report.errors.append(f"SKU {row['sku']}: existe, pero no es una silla")
            continue
        initial_stock = StockMovement.objects.filter(
            product=product, movement_type__code="CARGA_INICIAL"
        ).aggregate(total=Sum("quantity"))["total"]
        if not _matches(product, chair, row, values) or initial_stock != row["stock"]:
            report.errors.append(f"SKU {row['sku']}: difiere de la ficha ya importada")
            continue
        report.skipped += 1

    if report.errors or dry_run:
        transaction.set_rollback(True)
    return report
