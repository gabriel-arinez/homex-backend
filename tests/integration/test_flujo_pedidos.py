from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection, connections

from apps.catalogo.models import ConceptoCatalogo, Producto, ValorCatalogo
from apps.clientes.models import Cliente
from apps.movimientos_stock.models import MovimientoStock
from apps.pedidos.models import Pedido, TransicionEstadoPedido
from apps.pedidos.servicios import aprobar, cancelar, transicionar_pedido
from apps.proformas.models import DetalleProforma, Proforma
from apps.proformas.servicios import recalcular_proforma


@pytest.fixture
def setup():
    c = ConceptoCatalogo.objects.create(codigo="BASE")
    v = {
        x: ValorCatalogo.objects.create(concepto=c, codigo=x, nombre=x)
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
    u = get_user_model().objects.create_user(username="vendedor")
    cliente = Cliente.objects.create(tipo_cliente=v["PERSONA"], nombres="A")
    p = Producto.objects.create(categoria=v["SILLA"], nombre="Silla", stock=5, unidad_stock=v["PIEZA"])
    q = Proforma.objects.create(cliente=cliente, vendedor=u, estado=v["ENVIADA"], moneda=v["BOB"])
    DetalleProforma.objects.create(
        proforma=q,
        tipo_item=v["SILLA"],
        producto=p,
        nombre="Silla",
        cantidad=2,
        unidad=v["PIEZA"],
        precio_unitario=Decimal(10),
    )
    recalcular_proforma(q.id)
    return u, p, q


@pytest.mark.django_db
def test_approval_creates_pedido_sale_and_work_pedido(setup):
    u, p, q = setup
    pedido = aprobar(q.id, u.id)
    assert pedido.proforma_id == q.id and pedido.orden_trabajo.pedido_id == pedido.id
    p.refresh_from_db()
    assert p.stock == 3


@pytest.mark.django_db
def test_cancelarlation_restores_stock_once(setup):
    u, p, q = setup
    pedido = aprobar(q.id, u.id)
    cancelar(pedido.id, u.id)
    p.refresh_from_db()
    assert p.stock == 5
    assert MovimientoStock.objects.filter(referencia__isnull=False, pedido=pedido).count() == 1
    with pytest.raises(ValidationError):
        cancelar(pedido.id, u.id)


@pytest.mark.django_db
def test_approval_rejects_insufficient_stock_without_creating_pedido(setup):
    user, producto, proforma = setup
    producto.stock = 1
    producto.save(update_fields=["stock"])

    with pytest.raises(ValidationError, match="Stock insuficiente"):
        aprobar(proforma_id=proforma.pk, actor_id=user.pk)

    producto.refresh_from_db()
    assert producto.stock == 1
    assert not Pedido.objects.filter(proforma=proforma).exists()


@pytest.mark.django_db
def test_pedido_only_uses_configured_state_transitions(setup):
    user, _, proforma = setup
    pedido = aprobar(proforma_id=proforma.pk, actor_id=user.pk)
    confirmed = ValorCatalogo.objects.get(codigo="CONFIRMADO")
    in_production = ValorCatalogo.objects.create(
        concepto=confirmed.concepto, codigo="EN_PRODUCCION", nombre="En producción"
    )
    TransicionEstadoPedido.objects.create(origen=confirmed, destino=in_production)

    transicionar_pedido(pedido_id=pedido.pk, destino_codigo="EN_PRODUCCION")
    pedido.refresh_from_db()
    assert pedido.estado_id == in_production.pk

    with pytest.raises(ValidationError, match="Transición de pedido no permitida"):
        transicionar_pedido(pedido_id=pedido.pk, destino_codigo="CONFIRMADO")


@pytest.mark.django_db(transaction=True)
@pytest.mark.postgresql
@pytest.mark.skipif(
    connection.vendor != "postgresql", reason="requiere bloqueos por fila de PostgreSQL"
)
def test_only_one_approval_wins_the_last_unidad(setup):
    vendedor_one, producto, proforma_one = setup
    vendedor_two = get_user_model().objects.create_user(username="vendedor-two")
    proforma_two = Proforma.objects.create(
        cliente=proforma_one.cliente,
        vendedor=vendedor_two,
        estado=proforma_one.estado,
        moneda=proforma_one.moneda,
    )
    DetalleProforma.objects.create(
        proforma=proforma_two,
        tipo_item=ValorCatalogo.objects.get(codigo="SILLA"),
        producto=producto,
        nombre="Silla",
        cantidad=1,
        unidad=ValorCatalogo.objects.get(codigo="PIEZA"),
        precio_unitario=Decimal(10),
    )
    recalcular_proforma(proforma_two.pk)
    proforma_one.detalles.update(cantidad=5)

    def attempt(proforma_id, actor_id):
        connections.close_all()
        try:
            aprobar(proforma_id=proforma_id, actor_id=actor_id)
            return "aprobard"
        except ValidationError:
            return "insufficient_stock"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(
                lambda args: attempt(*args),
                ((proforma_one.pk, vendedor_one.pk), (proforma_two.pk, vendedor_two.pk)),
            )
        )

    producto.refresh_from_db()
    assert outcomes.count("aprobard") == 1
    assert outcomes.count("insufficient_stock") == 1
    assert producto.stock in {0, 4}
    assert Pedido.objects.count() == 1
