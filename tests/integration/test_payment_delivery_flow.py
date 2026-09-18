from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, connections, transaction
from rest_framework.test import APIClient

from apps.accounts.roles import SALES
from apps.catalog.models import CatalogConcept, CatalogValue, Product
from apps.customers.models import Customer
from apps.deliveries.models import DeliveryNote
from apps.deliveries.services import issue_delivery_note
from apps.documents.services import (
    render_delivery_note,
    render_quotation,
    render_receipt,
    render_work_order,
)
from apps.orders.models import OrderTransition
from apps.orders.services import approve, cancel, transition_order
from apps.payments.models import Receipt
from apps.payments.services import issue_receipt, void_receipt
from apps.quotations.models import Quotation, QuotationLine
from apps.quotations.services import recalculate_quotation


@pytest.fixture
def confirmed_order():
    concept = CatalogConcept.objects.create(code="BASE")
    values = {
        code: CatalogValue.objects.create(concept=concept, code=code, name=code)
        for code in (
            "ENVIADA",
            "APROBADA",
            "CONFIRMADO",
            "PENDIENTE",
            "CANCELADO",
            "VENTA",
            "REVERSA_VENTA",
            "BOB",
            "PERSONA",
            "PIEZA",
            "SILLA",
            "LISTO_ENTREGA",
            "EFECTIVO",
        )
    }
    seller = get_user_model().objects.create_user(username="seller")
    customer = Customer.objects.create(customer_type=values["PERSONA"], first_names="María")
    product = Product.objects.create(
        category=values["SILLA"], name="Silla", stock=4, stock_unit=values["PIEZA"]
    )
    quotation = Quotation.objects.create(
        customer=customer,
        seller=seller,
        status=values["ENVIADA"],
        currency=values["BOB"],
        customer_name_snapshot="María Cliente",
        customer_phone_snapshot="70000000",
    )
    QuotationLine.objects.create(
        quotation=quotation,
        item_type=values["SILLA"],
        product=product,
        name="Silla",
        quantity=1,
        unit=values["PIEZA"],
        unit_price=Decimal(100),
    )
    recalculate_quotation(quotation.pk)
    return seller, values, quotation, approve(quotation_id=quotation.pk, actor_id=seller.pk)


@pytest.mark.django_db
def test_issued_receipt_blocks_overpayment_and_cancellation(confirmed_order):
    seller, values, _, order = confirmed_order
    receipt = issue_receipt(
        order_id=order.pk,
        actor_id=seller.pk,
        full_name="María Cliente",
        amount_in_words="cincuenta bolivianos",
        concept="Anticipo",
        payment_type_id=values["EFECTIVO"].pk,
        current_payment=Decimal(50),
    )
    assert receipt.total == Decimal(100)
    assert receipt.on_account == Decimal(50)
    assert receipt.balance == Decimal(50)

    with pytest.raises(ValidationError, match="saldo pendiente"):
        issue_receipt(
            order_id=order.pk,
            actor_id=seller.pk,
            full_name="María Cliente",
            amount_in_words="sesenta bolivianos",
            concept="Pago",
            payment_type_id=values["EFECTIVO"].pk,
            current_payment=Decimal(60),
        )
    with pytest.raises(ValidationError, match="recibos emitidos"):
        cancel(order_id=order.pk, actor_id=seller.pk)


@pytest.mark.django_db
def test_voided_receipt_no_longer_blocks_a_new_payment_or_cancellation(confirmed_order):
    seller, values, _, order = confirmed_order
    receipt = issue_receipt(
        order_id=order.pk,
        actor_id=seller.pk,
        full_name="María Cliente",
        amount_in_words="cien bolivianos",
        concept="Pago por error",
        payment_type_id=values["EFECTIVO"].pk,
        current_payment=Decimal(100),
    )
    void_receipt(receipt_id=receipt.pk, actor_id=seller.pk)
    receipt.refresh_from_db()
    assert receipt.status == Receipt.Status.VOIDED

    replacement = issue_receipt(
        order_id=order.pk,
        actor_id=seller.pk,
        full_name="María Cliente",
        amount_in_words="cien bolivianos",
        concept="Pago correcto",
        payment_type_id=values["EFECTIVO"].pk,
        current_payment=Decimal(100),
    )
    assert replacement.on_account == Decimal(100)
    void_receipt(receipt_id=replacement.pk, actor_id=seller.pk)
    cancel(order_id=order.pk, actor_id=seller.pk)


@pytest.mark.django_db
def test_delivery_note_is_emitted_once_from_ready_order_and_documents_render(confirmed_order):
    seller, values, quotation, order = confirmed_order
    OrderTransition.objects.create(source=values["CONFIRMADO"], target=values["LISTO_ENTREGA"])
    transition_order(order_id=order.pk, target_code="LISTO_ENTREGA")
    note = issue_delivery_note(order_id=order.pk, seller_id=seller.pk, actor_id=seller.pk)
    assert note.number == 1
    assert DeliveryNote.objects.filter(order=order).count() == 1

    with pytest.raises(ValidationError, match="ya tiene"):
        issue_delivery_note(order_id=order.pk, seller_id=seller.pk, actor_id=seller.pk)

    receipt = issue_receipt(
        order_id=order.pk,
        actor_id=seller.pk,
        full_name="María Cliente",
        amount_in_words="cien bolivianos",
        concept="Pago",
        payment_type_id=values["EFECTIVO"].pk,
        current_payment=Decimal(100),
    )
    assert "María Cliente" in render_quotation(quotation.pk)
    assert "Orden de Trabajo" in render_work_order(order.workorder.pk)
    assert "Nota de Entrega" in render_delivery_note(note.pk)
    assert "Recibo" in render_receipt(receipt.pk)


@pytest.mark.django_db
def test_receipt_api_uses_the_protected_payment_service(confirmed_order):
    seller, values, _, order = confirmed_order
    seller.groups.add(Group.objects.get(name=SALES))
    client = APIClient()
    client.force_authenticate(seller)
    response = client.post(
        "/api/v1/receipts/",
        {
            "order": order.pk,
            "full_name": "María Cliente",
            "amount_in_words": "cincuenta bolivianos",
            "concept": "Anticipo",
            "payment_type": values["EFECTIVO"].pk,
            "current_payment": "50.00",
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.data["status"] == Receipt.Status.ISSUED

    response = client.post(f"/api/v1/receipts/{response.data['id']}/void/", format="json")
    assert response.status_code == 200
    assert response.data["status"] == Receipt.Status.VOIDED


@pytest.mark.django_db
def test_receipt_api_rejects_an_authenticated_user_without_commercial_role(confirmed_order):
    seller, values, _, order = confirmed_order
    client = APIClient()
    client.force_authenticate(seller)

    response = client.post(
        "/api/v1/receipts/",
        {
            "order": order.pk,
            "full_name": "María Cliente",
            "amount_in_words": "cincuenta bolivianos",
            "concept": "Anticipo",
            "payment_type": values["EFECTIVO"].pk,
            "current_payment": "50.00",
        },
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db(transaction=True)
@pytest.mark.postgresql
@pytest.mark.skipif(
    connection.vendor != "postgresql", reason="requiere bloqueos por fila de PostgreSQL"
)
def test_concurrent_receipts_cannot_overpay(confirmed_order):
    seller, values, _, order = confirmed_order

    def attempt():
        connections.close_all()
        try:
            issue_receipt(
                order_id=order.pk,
                actor_id=seller.pk,
                full_name="María Cliente",
                amount_in_words="sesenta bolivianos",
                concept="Pago",
                payment_type_id=values["EFECTIVO"].pk,
                current_payment=Decimal(60),
            )
            return "issued"
        except ValidationError:
            return "rejected"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: attempt(), range(2)))

    assert outcomes.count("issued") == 1
    assert outcomes.count("rejected") == 1
    assert Receipt.objects.filter(status=Receipt.Status.ISSUED).count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.postgresql
@pytest.mark.skipif(connection.vendor != "postgresql", reason="requiere triggers de PostgreSQL")
def test_postgresql_only_allows_voiding_an_issued_receipt(confirmed_order):
    seller, values, _, order = confirmed_order
    receipt = issue_receipt(
        order_id=order.pk,
        actor_id=seller.pk,
        full_name="María Cliente",
        amount_in_words="cien bolivianos",
        concept="Pago",
        payment_type_id=values["EFECTIVO"].pk,
        current_payment=Decimal(100),
    )

    receipt.concept = "Concepto alterado"
    with pytest.raises(DatabaseError, match="evidencia"), transaction.atomic():
        receipt.save(update_fields=["concept"])

    with pytest.raises(DatabaseError, match="no se eliminan"), transaction.atomic():
        receipt.delete()

    void_receipt(receipt_id=receipt.pk, actor_id=seller.pk)
    receipt.refresh_from_db()
    assert receipt.status == Receipt.Status.VOIDED
