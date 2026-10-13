"""AP2: regresiones API y PostgreSQL sobre efectos comerciales irreversibles.

Los casos verifican el estado persistido, no únicamente códigos HTTP.
Se ejecutan con el PostgreSQL real provisionado en CI.
"""

import pytest
from rest_framework.test import APIClient

from apps.movimientos_stock.models import MovimientoStock
from apps.ordenes_trabajo.models import OrdenTrabajo
from apps.pedidos.models import Pedido
from apps.proformas.services import crear_proforma
from apps.recibos.models import Recibo
from tests.api.test_f073_api import preparar_proforma_enviada
from tests.factories import cargar_stock, cliente_persona, silla, valor, vendedor


@pytest.mark.django_db(transaction=True)
def test_ap2_aprobacion_api_sin_stock_revierte_todos_los_efectos(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap2-sin-stock"))
    producto = silla(actor, sku="AP2-ULTIMA-SIN-STOCK")
    proforma = preparar_proforma_enviada(actor, producto)

    client = APIClient()
    client.force_authenticate(actor)
    response = client.post(f"/api/v1/proformas/{proforma.pk}/aprobar/", format="json")

    assert response.status_code == 409
    proforma.refresh_from_db()
    producto.refresh_from_db()
    assert proforma.estado.codigo == "ENVIADA"
    assert producto.stock == 0
    assert not Pedido.objects.filter(proforma=proforma).exists()
    assert not OrdenTrabajo.objects.filter(pedido__proforma=proforma).exists()
    assert not MovimientoStock.objects.filter(pedido__proforma=proforma).exists()


@pytest.mark.django_db(transaction=True)
def test_ap2_doble_post_aprobacion_no_duplica_stock_ni_ot(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap2-post-repetido"))
    producto = silla(actor, sku="AP2-POST-REPETIDO")
    cargar_stock(producto, actor, 2)
    proforma = preparar_proforma_enviada(actor, producto)

    client = APIClient()
    client.force_authenticate(actor)
    endpoint = f"/api/v1/proformas/{proforma.pk}/aprobar/"
    first = client.post(endpoint, format="json")
    second = client.post(endpoint, format="json")

    assert first.status_code == 200
    assert second.status_code == 409
    pedido = Pedido.objects.get(proforma=proforma)
    assert pedido.pk == first.data["pedido_id"]
    assert OrdenTrabajo.objects.filter(pedido=pedido).count() == 1
    assert MovimientoStock.objects.filter(
        pedido=pedido, tipo_movimiento=valor("TIPO_MOVIMIENTO", "VENTA"),
        cantidad=-1,
    ).count() == 1
    producto.refresh_from_db()
    assert producto.stock == 1


@pytest.mark.django_db(transaction=True)
def test_ap2_listado_y_aprobacion_no_filtran_datos_entre_vendedores(django_user_model):
    propietario = vendedor(django_user_model.objects.create_user(username="ap2-dueno"))
    ajeno = vendedor(django_user_model.objects.create_user(username="ap2-ajeno"))
    admin = django_user_model.objects.create_user(username="ap2-admin", is_staff=True)
    producto = silla(propietario, sku="AP2-IDOR")
    cargar_stock(producto, propietario, 1)
    privada = preparar_proforma_enviada(propietario, producto)
    propia = crear_proforma(actor=ajeno, cliente=cliente_persona(ajeno))

    client = APIClient()
    client.force_authenticate(ajeno)
    listing = client.get("/api/v1/proformas/", {"page_size": 50})
    assert listing.status_code == 200
    visibles = {fila["id"] for fila in listing.data["results"]}
    assert propia.id in visibles
    assert privada.id not in visibles

    response = client.post(f"/api/v1/proformas/{privada.pk}/aprobar/", format="json")
    assert response.status_code == 404
    privada.refresh_from_db()
    producto.refresh_from_db()
    assert privada.estado.codigo == "ENVIADA"
    assert producto.stock == 1
    assert not Pedido.objects.filter(proforma=privada).exists()

    client.force_authenticate(admin)
    administracion = client.get("/api/v1/proformas/", {"page_size": 50})
    assert administracion.status_code == 200
    ids_admin = {fila["id"] for fila in administracion.data["results"]}
    assert {privada.id, propia.id} <= ids_admin


@pytest.mark.django_db(transaction=True)
def test_ap2_cancelacion_con_recibo_emitido_no_crea_reversa(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap2-cobro-cancelacion"))
    producto = silla(actor, sku="AP2-COBRO-CANCELACION")
    cargar_stock(producto, actor, 1)
    proforma = preparar_proforma_enviada(actor, producto)
    client = APIClient()
    client.force_authenticate(actor)
    approved = client.post(f"/api/v1/proformas/{proforma.pk}/aprobar/", format="json")
    assert approved.status_code == 200
    pedido = Pedido.objects.get(pk=approved.data["pedido_id"])
    pago = client.post(
        f"/api/v1/pedidos/{pedido.pk}/emitir_recibo/",
        {
            "nombre_completo": "Ana López",
            "monto_en_letras": "diez bolivianos",
            "concepto": "Anticipo",
            "tipo_pago": valor("TIPO_PAGO", "EFECTIVO").pk,
            "pago_actual": "10.00",
        },
        format="json",
    )
    assert pago.status_code == 201

    before = MovimientoStock.objects.filter(
        movimiento_referencia__pedido=pedido,
        tipo_movimiento=valor("TIPO_MOVIMIENTO", "REVERSA_VENTA"),
    ).count()
    cancellation = client.post(f"/api/v1/pedidos/{pedido.pk}/cancelar/", format="json")
    assert cancellation.status_code == 400
    pedido.refresh_from_db()
    producto.refresh_from_db()
    assert pedido.estado.codigo == "CONFIRMADO"
    assert producto.stock == 0
    assert Recibo.objects.filter(pedido=pedido, estado="EMITIDO").count() == 1
    assert MovimientoStock.objects.filter(
        movimiento_referencia__pedido=pedido,
        tipo_movimiento=valor("TIPO_MOVIMIENTO", "REVERSA_VENTA"),
    ).count() == before == 0
