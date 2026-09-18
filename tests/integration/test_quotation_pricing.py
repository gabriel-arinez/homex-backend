from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.catalog.models import CatalogConcept, CatalogValue
from apps.customers.models import Customer
from apps.quotations.models import Quotation, QuotationLine
from apps.quotations.services import recalculate_quotation


@pytest.mark.django_db
def test_negotiated_total_is_authoritative() -> None:
    concept = CatalogConcept.objects.create(code="BASE")
    state = CatalogValue.objects.create(concept=concept, code="BORRADOR", name="Borrador")
    currency = CatalogValue.objects.create(concept=concept, code="BOB", name="Boliviano")
    item_type = CatalogValue.objects.create(concept=concept, code="MUEBLE_MEDIDA", name="Mueble")
    unit = CatalogValue.objects.create(concept=concept, code="PIEZA", name="Pieza")
    customer_type = CatalogValue.objects.create(concept=concept, code="PERSONA", name="Persona")
    user = get_user_model().objects.create_user(username="seller")
    customer = Customer.objects.create(
        customer_type=customer_type, first_names="Ana", last_names="Lopez"
    )
    quotation = Quotation.objects.create(
        customer=customer, seller=user, status=state, currency=currency
    )
    QuotationLine.objects.create(
        quotation=quotation,
        item_type=item_type,
        name="Mueble",
        quantity=3,
        unit=unit,
        calculation_mode="TOTAL_NEGOCIADO",
        negotiated_amount=Decimal("100.00"),
    )
    quotation = recalculate_quotation(quotation.id)
    assert quotation.total == Decimal("100.00")


@pytest.mark.django_db
def test_unit_price_calculation_is_distinct() -> None:
    concept = CatalogConcept.objects.create(code="BASE")
    values = {
        code: CatalogValue.objects.create(concept=concept, code=code, name=code)
        for code in ("BORRADOR", "BOB", "MUEBLE_MEDIDA", "PIEZA", "PERSONA")
    }
    user = get_user_model().objects.create_user(username="seller")
    customer = Customer.objects.create(
        customer_type=values["PERSONA"], first_names="Ana", last_names="Lopez"
    )
    quotation = Quotation.objects.create(
        customer=customer, seller=user, status=values["BORRADOR"], currency=values["BOB"]
    )
    QuotationLine.objects.create(
        quotation=quotation,
        item_type=values["MUEBLE_MEDIDA"],
        name="Mueble",
        quantity=2,
        unit=values["PIEZA"],
        unit_price=Decimal("50.00"),
        discount=Decimal("5.00"),
    )
    assert recalculate_quotation(quotation.id).total == Decimal("95.00")


@pytest.mark.django_db
def test_submit_freezes_customer_snapshot() -> None:
    from apps.quotations.services import submit_quotation

    concept = CatalogConcept.objects.create(code="BASE")
    values = {
        code: CatalogValue.objects.create(concept=concept, code=code, name=code)
        for code in ("BORRADOR", "ENVIADA", "BOB", "PERSONA")
    }
    user = get_user_model().objects.create_user(username="seller")
    customer = Customer.objects.create(
        customer_type=values["PERSONA"], first_names="Ana", last_names="Lopez", phone="70000000"
    )
    quotation = Quotation.objects.create(
        customer=customer, seller=user, status=values["BORRADOR"], currency=values["BOB"]
    )
    submitted = submit_quotation(quotation.id, user.id)
    assert submitted.status.code == "ENVIADA"
    assert submitted.customer_name_snapshot == "Ana Lopez"
    customer.first_names = "Cambio"
    customer.save()
    assert Quotation.objects.get(pk=quotation.id).customer_name_snapshot == "Ana Lopez"
