from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, connections, transaction
from rest_framework.test import APIClient

from apps.accounts.roles import SALES
from apps.catalogo.models import ConceptoCatalogo, Producto, ValorCatalogo
from apps.clientes.models import Cliente
from apps.documentos.servicios import (
    renderizar_nota_entrega,
    renderizar_orden_trabajo,
    renderizar_proforma,
    renderizar_recibo,
)
from apps.notas_entrega.models import NotaEntrega
from apps.notas_entrega.servicios import emitir_nota_entrega
from apps.pedidos.models import TransicionEstadoPedido
from apps.pedidos.servicios import aprobar, cancelar, transicionar_pedido
from apps.proformas.models import DetalleProforma, Proforma
from apps.proformas.servicios import recalcular_proforma
from apps.recibos.models import Recibo
from apps.recibos.servicios import anular_recibo, emitir_recibo


@pytest.fixture
def confirmed_pedido():
    concepto = ConceptoCatalogo.objects.create(codigo="BASE")
    values = {
        codigo: ValorCatalogo.objects.create(concepto=concepto, codigo=codigo, nombre=codigo)
        for codigo in (
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
    vendedor = get_user_model().objects.create_user(username="vendedor")
    cliente = Cliente.objects.create(tipo_cliente=values["PERSONA"], nombres="María")
    producto = Producto.objects.create(
        categoria=values["SILLA"], nombre="Silla", stock=4, unidad_stock=values["PIEZA"]
    )
    proforma = Proforma.objects.create(
        cliente=cliente,
        vendedor=vendedor,
        estado=values["ENVIADA"],
        moneda=values["BOB"],
        cliente_nombre_snapshot="María Cliente",
        cliente_celular_snapshot="70000000",
    )
    DetalleProforma.objects.create(
        proforma=proforma,
        tipo_item=values["SILLA"],
        producto=producto,
        nombre="Silla",
        cantidad=1,
        unidad=values["PIEZA"],
        precio_unitario=Decimal(100),
    )
    recalcular_proforma(proforma.pk)
    return vendedor, values, proforma, aprobar(proforma_id=proforma.pk, actor_id=vendedor.pk)


@pytest.mark.django_db
def test_issued_receipt_blocks_overpayment_and_cancelarlation(confirmed_pedido):
    vendedor, values, _, pedido = confirmed_pedido
    receipt = emitir_recibo(
        pedido_id=pedido.pk,
        actor_id=vendedor.pk,
        nombre_completo="María Cliente",
        monto_literal="cincuenta bolivianos",
        concepto="Anticipo",
        tipo_pago_id=values["EFECTIVO"].pk,
        pago_actual=Decimal(50),
    )
    assert receipt.total == Decimal(100)
    assert receipt.a_cuenta == Decimal(50)
    assert receipt.saldo == Decimal(50)

    with pytest.raises(ValidationError, match="saldo pendiente"):
        emitir_recibo(
            pedido_id=pedido.pk,
            actor_id=vendedor.pk,
            nombre_completo="María Cliente",
            monto_literal="sesenta bolivianos",
            concepto="Pago",
            tipo_pago_id=values["EFECTIVO"].pk,
            pago_actual=Decimal(60),
        )
    with pytest.raises(ValidationError, match="recibos emitidos"):
        cancelar(pedido_id=pedido.pk, actor_id=vendedor.pk)


@pytest.mark.django_db
def test_voided_receipt_no_longer_blocks_a_new_payment_or_cancelarlation(confirmed_pedido):
    vendedor, values, _, pedido = confirmed_pedido
    receipt = emitir_recibo(
        pedido_id=pedido.pk,
        actor_id=vendedor.pk,
        nombre_completo="María Cliente",
        monto_literal="cien bolivianos",
        concepto="Pago por error",
        tipo_pago_id=values["EFECTIVO"].pk,
        pago_actual=Decimal(100),
    )
    anular_recibo(recibo_id=receipt.pk, actor_id=vendedor.pk)
    receipt.refresh_from_db()
    assert receipt.estado == Recibo.Status.VOIDED

    replacement = emitir_recibo(
        pedido_id=pedido.pk,
        actor_id=vendedor.pk,
        nombre_completo="María Cliente",
        monto_literal="cien bolivianos",
        concepto="Pago correcto",
        tipo_pago_id=values["EFECTIVO"].pk,
        pago_actual=Decimal(100),
    )
    assert replacement.a_cuenta == Decimal(100)
    anular_recibo(recibo_id=replacement.pk, actor_id=vendedor.pk)
    cancelar(pedido_id=pedido.pk, actor_id=vendedor.pk)


@pytest.mark.django_db
def test_delivery_note_is_emitted_once_from_ready_pedido_and_documents_render(confirmed_pedido):
    vendedor, values, proforma, pedido = confirmed_pedido
    TransicionEstadoPedido.objects.create(
        origen=values["CONFIRMADO"], destino=values["LISTO_ENTREGA"]
    )
    transicionar_pedido(pedido_id=pedido.pk, destino_codigo="LISTO_ENTREGA")
    note = emitir_nota_entrega(pedido_id=pedido.pk, vendedor_id=vendedor.pk, actor_id=vendedor.pk)
    assert note.numero == 1
    assert NotaEntrega.objects.filter(pedido=pedido).count() == 1

    with pytest.raises(ValidationError, match="ya tiene"):
        emitir_nota_entrega(pedido_id=pedido.pk, vendedor_id=vendedor.pk, actor_id=vendedor.pk)

    receipt = emitir_recibo(
        pedido_id=pedido.pk,
        actor_id=vendedor.pk,
        nombre_completo="María Cliente",
        monto_literal="cien bolivianos",
        concepto="Pago",
        tipo_pago_id=values["EFECTIVO"].pk,
        pago_actual=Decimal(100),
    )
    assert "María Cliente" in renderizar_proforma(proforma.pk)
    assert "Orden de Trabajo" in renderizar_orden_trabajo(pedido.orden_trabajo.pk)
    assert "Nota de Entrega" in renderizar_nota_entrega(note.pk)
    assert "Recibo" in renderizar_recibo(receipt.pk)


@pytest.mark.django_db
def test_receipt_api_uses_the_protected_payment_service(confirmed_pedido):
    vendedor, values, _, pedido = confirmed_pedido
    vendedor.groups.add(Group.objects.get(name=SALES))
    client = APIClient()
    client.force_authenticate(vendedor)
    response = client.post(
        "/api/v1/recibos/",
        {
            "pedido": pedido.pk,
            "nombre_completo": "María Cliente",
            "monto_literal": "cincuenta bolivianos",
            "concepto": "Anticipo",
            "tipo_pago": values["EFECTIVO"].pk,
            "pago_actual": "50.00",
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.data["estado"] == Recibo.Status.ISSUED

    response = client.post(f"/api/v1/recibos/{response.data['id']}/anular/", format="json")
    assert response.status_code == 200
    assert response.data["estado"] == Recibo.Status.VOIDED


@pytest.mark.django_db
def test_receipt_api_rejects_an_authenticated_user_without_commercial_role(confirmed_pedido):
    vendedor, values, _, pedido = confirmed_pedido
    client = APIClient()
    client.force_authenticate(vendedor)

    response = client.post(
        "/api/v1/recibos/",
        {
            "pedido": pedido.pk,
            "nombre_completo": "María Cliente",
            "monto_literal": "cincuenta bolivianos",
            "concepto": "Anticipo",
            "tipo_pago": values["EFECTIVO"].pk,
            "pago_actual": "50.00",
        },
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db(transaction=True)
@pytest.mark.postgresql
@pytest.mark.skipif(
    connection.vendor != "postgresql", reason="requiere bloqueos por fila de PostgreSQL"
)
def test_concurrent_receipts_cannot_overpay(confirmed_pedido):
    vendedor, values, _, pedido = confirmed_pedido

    def attempt():
        connections.close_all()
        try:
            emitir_recibo(
                pedido_id=pedido.pk,
                actor_id=vendedor.pk,
                nombre_completo="María Cliente",
                monto_literal="sesenta bolivianos",
                concepto="Pago",
                tipo_pago_id=values["EFECTIVO"].pk,
                pago_actual=Decimal(60),
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
    assert Recibo.objects.filter(estado=Recibo.Status.ISSUED).count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.postgresql
@pytest.mark.skipif(connection.vendor != "postgresql", reason="requiere triggers de PostgreSQL")
def test_postgresql_only_allows_voiding_an_issued_receipt(confirmed_pedido):
    vendedor, values, _, pedido = confirmed_pedido
    receipt = emitir_recibo(
        pedido_id=pedido.pk,
        actor_id=vendedor.pk,
        nombre_completo="María Cliente",
        monto_literal="cien bolivianos",
        concepto="Pago",
        tipo_pago_id=values["EFECTIVO"].pk,
        pago_actual=Decimal(100),
    )

    receipt.concepto = "Concepto alterado"
    with pytest.raises(DatabaseError, match="evidencia"), transaction.atomic():
        receipt.save(update_fields=["concepto"])

    with pytest.raises(DatabaseError, match="no se eliminan"), transaction.atomic():
        receipt.delete()

    anular_recibo(recibo_id=receipt.pk, actor_id=vendedor.pk)
    receipt.refresh_from_db()
    assert receipt.estado == Recibo.Status.VOIDED
