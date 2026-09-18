import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog.models import CatalogConcept, CatalogValue, ChairProduct, Product
from apps.inventory.models import StockMovement


@pytest.fixture
def import_catalog():
    values = {}
    for concept_code, codes in {
        "CATEGORIA_PRODUCTO": {"SILLA": "Silla"},
        "UNIDAD_MEDIDA": {"PIEZA": "Pieza"},
        "TIPO_MOVIMIENTO": {"CARGA_INICIAL": "Carga inicial"},
        "MARCA": {"HOMEX": "HOMEX"},
        "COLOR": {"NEGRO": "Negro", "GRIS": "Gris"},
    }.items():
        concept = CatalogConcept.objects.create(code=concept_code)
        for code, name in codes.items():
            values[(concept_code, code)] = CatalogValue.objects.create(
                concept=concept, code=code, name=name
            )
    return values


def write_rows(tmp_path, rows):
    input_path = tmp_path / "sillas.json"
    input_path.write_text(json.dumps(rows), encoding="utf-8")
    return input_path


@pytest.mark.django_db
def test_chair_import_is_dry_run_then_idempotent(tmp_path, import_catalog):
    input_path = write_rows(
        tmp_path,
        [
            {
                "sku": "B15-NEGRO",
                "name": "Silla B15 negra",
                "list_price": "1500.00",
                "stock": 3,
                "brand_code": "HOMEX",
                "model": "B15",
                "primary_color_code": "NEGRO",
                "secondary_color_code": "GRIS",
                "specifications": {"material": "malla"},
            }
        ],
    )
    output = StringIO()
    call_command("import_sillas", input=str(input_path), dry_run=True, stdout=output)
    assert "creados=1" in output.getvalue()
    assert Product.objects.count() == 0

    call_command("import_sillas", input=str(input_path), stdout=output)
    product = Product.objects.get(sku="B15-NEGRO")
    assert product.stock == 3
    assert ChairProduct.objects.get(product=product).model == "B15"
    assert StockMovement.objects.get(product=product).movement_type.code == "CARGA_INICIAL"

    call_command("import_sillas", input=str(input_path), stdout=output)
    assert Product.objects.count() == 1
    assert StockMovement.objects.filter(product=product).count() == 1
    assert "omitidos=1" in output.getvalue()


@pytest.mark.django_db
def test_chair_import_rejects_missing_commercial_identity(tmp_path, import_catalog):
    input_path = write_rows(tmp_path, [{"text": "Silla Ejecutiva", "label": []}])
    with pytest.raises(CommandError, match="no se aplicó"):
        call_command("import_sillas", input=str(input_path), dry_run=True)
    assert Product.objects.count() == 0


@pytest.mark.django_db
def test_catalog_price_and_reference_availability(import_catalog):
    from datetime import date
    from decimal import Decimal

    from apps.catalog.models import ProductDiscount
    from apps.catalog.queries import product_availability, product_price
    from apps.quotations.models import Quotation, QuotationLine

    status_concept = CatalogConcept.objects.create(code="ESTADO_PROFORMA")
    sent = CatalogValue.objects.create(concept=status_concept, code="ENVIADA", name="Enviada")
    currency_concept = CatalogConcept.objects.create(code="MONEDA")
    bob = CatalogValue.objects.create(concept=currency_concept, code="BOB", name="Boliviano")
    customer_concept = CatalogConcept.objects.create(code="TIPO_CLIENTE")
    person = CatalogValue.objects.create(concept=customer_concept, code="PERSONA", name="Persona")
    item_concept = CatalogConcept.objects.create(code="TIPO_ITEM")
    chair_item = CatalogValue.objects.create(concept=item_concept, code="SILLA", name="Silla")
    from django.contrib.auth import get_user_model

    from apps.customers.models import Customer

    seller = get_user_model().objects.create_user(username="availability-seller")
    customer = Customer.objects.create(customer_type=person, first_names="Cliente")
    product = Product.objects.create(
        sku="B15-NEGRO",
        category=import_catalog[("CATEGORIA_PRODUCTO", "SILLA")],
        name="Silla B15",
        list_price=Decimal(1500),
        stock=8,
        stock_unit=import_catalog[("UNIDAD_MEDIDA", "PIEZA")],
    )
    quotation = Quotation.objects.create(
        customer=customer, seller=seller, status=sent, currency=bob
    )
    QuotationLine.objects.create(
        quotation=quotation,
        item_type=chair_item,
        product=product,
        name="Silla B15",
        quantity=3,
        unit=import_catalog[("UNIDAD_MEDIDA", "PIEZA")],
        unit_price=Decimal(1500),
    )
    ProductDiscount.objects.create(
        product=product,
        price_before=Decimal(1500),
        price_now=Decimal(1200),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )

    assert product_availability(product).reference_availability == 5
    assert product_price(product, on_date=date(2026, 6, 1)).effective_price == Decimal(1200)
