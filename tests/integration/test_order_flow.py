from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection, connections

from apps.catalog.models import CatalogConcept, CatalogValue, Product
from apps.customers.models import Customer
from apps.inventory.models import StockMovement
from apps.orders.models import Order, OrderTransition
from apps.orders.services import approve, cancel, transition_order
from apps.quotations.models import Quotation, QuotationLine
from apps.quotations.services import recalculate_quotation


@pytest.fixture
def setup():
    c = CatalogConcept.objects.create(code="BASE")
    v = {
        x: CatalogValue.objects.create(concept=c, code=x, name=x)
        for x in (
            "ENVIADA",
            "APROBADA",
            "CONFIRMADO",
            "PENDIENTE",
            "CANCELADO",
            "VENTA",
            "REVERSA_VENTA",
            "BOB",
            "PERSONA",
            "MUEBLE_MEDIDA",
            "PIEZA",
            "SILLA",
        )
    }
    u = get_user_model().objects.create_user(username="seller")
    customer = Customer.objects.create(customer_type=v["PERSONA"], first_names="A")
    p = Product.objects.create(category=v["SILLA"], name="Silla", stock=5, stock_unit=v["PIEZA"])
    q = Quotation.objects.create(
        customer=customer, seller=u, status=v["ENVIADA"], currency=v["BOB"]
    )
    QuotationLine.objects.create(
        quotation=q,
        item_type=v["SILLA"],
        product=p,
        name="Silla",
        quantity=2,
        unit=v["PIEZA"],
        unit_price=Decimal(10),
    )
    recalculate_quotation(q.id)
    return u, p, q


@pytest.mark.django_db
def test_approval_creates_order_sale_and_work_order(setup):
    u, p, q = setup
    order = approve(q.id, u.id)
    assert order.quotation_id == q.id and order.workorder.order_id == order.id
    p.refresh_from_db()
    assert p.stock == 3


@pytest.mark.django_db
def test_cancellation_restores_stock_once(setup):
    u, p, q = setup
    order = approve(q.id, u.id)
    cancel(order.id, u.id)
    p.refresh_from_db()
    assert p.stock == 5
    assert StockMovement.objects.filter(reference__isnull=False, order=order).count() == 1
    with pytest.raises(ValidationError):
        cancel(order.id, u.id)


@pytest.mark.django_db
def test_approval_rejects_insufficient_stock_without_creating_order(setup):
    user, product, quotation = setup
    product.stock = 1
    product.save(update_fields=["stock"])

    with pytest.raises(ValidationError, match="Stock insuficiente"):
        approve(quotation_id=quotation.pk, actor_id=user.pk)

    product.refresh_from_db()
    assert product.stock == 1
    assert not Order.objects.filter(quotation=quotation).exists()


@pytest.mark.django_db
def test_order_only_uses_configured_state_transitions(setup):
    user, _, quotation = setup
    order = approve(quotation_id=quotation.pk, actor_id=user.pk)
    confirmed = CatalogValue.objects.get(code="CONFIRMADO")
    in_production = CatalogValue.objects.create(
        concept=confirmed.concept, code="EN_PRODUCCION", name="En producción"
    )
    OrderTransition.objects.create(source=confirmed, target=in_production)

    transition_order(order_id=order.pk, target_code="EN_PRODUCCION")
    order.refresh_from_db()
    assert order.status_id == in_production.pk

    with pytest.raises(ValidationError, match="Transición de pedido no permitida"):
        transition_order(order_id=order.pk, target_code="CONFIRMADO")


@pytest.mark.django_db(transaction=True)
@pytest.mark.postgresql
@pytest.mark.skipif(
    connection.vendor != "postgresql", reason="requiere bloqueos por fila de PostgreSQL"
)
def test_only_one_approval_wins_the_last_unit(setup):
    seller_one, product, quotation_one = setup
    seller_two = get_user_model().objects.create_user(username="seller-two")
    quotation_two = Quotation.objects.create(
        customer=quotation_one.customer,
        seller=seller_two,
        status=quotation_one.status,
        currency=quotation_one.currency,
    )
    QuotationLine.objects.create(
        quotation=quotation_two,
        item_type=CatalogValue.objects.get(code="SILLA"),
        product=product,
        name="Silla",
        quantity=1,
        unit=CatalogValue.objects.get(code="PIEZA"),
        unit_price=Decimal(10),
    )
    recalculate_quotation(quotation_two.pk)
    quotation_one.lines.update(quantity=5)

    def attempt(quotation_id, actor_id):
        connections.close_all()
        try:
            approve(quotation_id=quotation_id, actor_id=actor_id)
            return "approved"
        except ValidationError:
            return "insufficient_stock"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(
                lambda args: attempt(*args),
                ((quotation_one.pk, seller_one.pk), (quotation_two.pk, seller_two.pk)),
            )
        )

    product.refresh_from_db()
    assert outcomes.count("approved") == 1
    assert outcomes.count("insufficient_stock") == 1
    assert product.stock in {0, 4}
    assert Order.objects.count() == 1
