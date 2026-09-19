import pytest
from rest_framework.test import APIClient

from apps.movimientos_stock.models import MovimientoStock
from apps.notas_entrega.models import NotaEntrega
from apps.ordenes_trabajo.models import OrdenTrabajo
from apps.pedidos.models import Pedido
from apps.recibos.models import Recibo
from tests.factories import cargar_stock, silla, valor, vendedor


def autenticar_jwt(cliente, *, username, password):
    respuesta = cliente.post(
        "/api/v1/auth/token/",
        {
            "username": username,
            "password": password,
        },
        format="json",
    )

    assert respuesta.status_code == 200
    assert "access" in respuesta.data

    cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {respuesta.data['access']}")


def crear_cliente_api(cliente, *, sufijo=""):
    respuesta = cliente.post(
        "/api/v1/clientes/",
        {
            "tipo_cliente": valor(
                "TIPO_CLIENTE",
                "PERSONA",
            ).id,
            "nombres": f"Ana{sufijo}",
            "apellidos": "López",
            "celular": "70000000",
            "direccion": "La Paz",
        },
        format="json",
    )

    assert respuesta.status_code == 201

    return respuesta.data["id"]


def crear_proforma_api(
    cliente,
    *,
    cliente_id,
    producto,
):
    respuesta = cliente.post(
        "/api/v1/proformas/",
        {
            "cliente": cliente_id,
            "moneda_codigo": "BOB",
        },
        format="json",
    )

    assert respuesta.status_code == 201

    proforma_id = respuesta.data["id"]

    respuesta = cliente.post(
        f"/api/v1/proformas/{proforma_id}/detalles/",
        {
            "tipo_item": valor(
                "TIPO_ITEM",
                "SILLA",
            ).id,
            "producto": producto.id,
            "nombre": producto.nombre,
            "cantidad": 1,
            "unidad": valor(
                "UNIDAD_MEDIDA",
                "PIEZA",
            ).id,
            "modo_calculo": "PRECIO_UNITARIO",
            "precio_unitario": str(producto.precio_lista),
            "descuento": "0.00",
        },
        format="json",
    )

    assert respuesta.status_code == 201

    respuesta = cliente.post(
        f"/api/v1/proformas/{proforma_id}/enviar/",
        format="json",
    )

    assert respuesta.status_code == 200
    assert (
        respuesta.data["estado"]
        == valor(
            "ESTADO_PROFORMA",
            "ENVIADA",
        ).id
    )

    respuesta = cliente.post(
        f"/api/v1/proformas/{proforma_id}/aprobar/",
        format="json",
    )

    assert respuesta.status_code == 200
    assert respuesta.data["estado"] == "CONFIRMADO"

    return Pedido.objects.get(
        id=respuesta.data["pedido_id"],
    )


@pytest.mark.django_db(transaction=True)
def test_recorrido_comercial_e2e_api_jwt_y_cancelacion_sin_cobro(
    django_user_model,
):
    username = "e2e-vendedor"
    password = "F076-e2e-password-seguro"

    actor = vendedor(
        django_user_model.objects.create_user(
            username=username,
            password=password,
        )
    )

    # Fixtures maestras: catálogo y stock no son operaciones de vendedor.
    producto = silla(
        actor,
        sku="E2E-SILLA",
        precio="50.00",
    )
    cargar_stock(
        producto,
        actor,
        2,
    )

    producto_cancelable = silla(
        actor,
        sku="E2E-CANCELAR",
        precio="20.00",
    )
    cargar_stock(
        producto_cancelable,
        actor,
        1,
    )

    cliente = APIClient()

    # 1. Login JWT real.
    autenticar_jwt(
        cliente,
        username=username,
        password=password,
    )

    # 2. Cliente vía API.
    cliente_id = crear_cliente_api(
        cliente,
    )

    # 3. Catálogo vía API.
    respuesta = cliente.get(f"/api/v1/catalogo/productos/{producto.id}/")

    assert respuesta.status_code == 200
    assert respuesta.data["sku"] == "E2E-SILLA"

    # 4. Proforma + detalle + envío + aprobación vía API.
    pedido = crear_proforma_api(
        cliente,
        cliente_id=cliente_id,
        producto=producto,
    )

    pedido.refresh_from_db()
    producto.refresh_from_db()

    assert pedido.estado.codigo == "CONFIRMADO"
    assert producto.stock == 1

    # PostgreSQL debió materializar exactamente VENTA + OT.
    venta = MovimientoStock.objects.get(
        pedido=pedido,
        tipo_movimiento=valor(
            "TIPO_MOVIMIENTO",
            "VENTA",
        ),
    )

    assert venta.producto_id == producto.id
    assert venta.cantidad == -1

    orden = OrdenTrabajo.objects.get(
        pedido=pedido,
    )

    assert orden.estado.codigo == "PENDIENTE"

    # 5. Recibo mientras el pedido está CONFIRMADO (P27).
    respuesta = cliente.post(
        f"/api/v1/pedidos/{pedido.id}/emitir_recibo/",
        {
            "nombre_completo": "Ana López",
            "monto_en_letras": "cincuenta bolivianos",
            "concepto": "Pago total",
            "tipo_pago": valor(
                "TIPO_PAGO",
                "EFECTIVO",
            ).id,
            "pago_actual": "50.00",
        },
        format="json",
    )

    assert respuesta.status_code == 201

    recibo = Recibo.objects.get(
        id=respuesta.data["id"],
    )

    assert recibo.estado == "EMITIDO"
    assert str(recibo.pago_actual) == "50.00"
    assert str(recibo.saldo) == "0.00"

    # 6. CONFIRMADO -> EN_PRODUCCION vía API.
    respuesta = cliente.post(
        f"/api/v1/pedidos/{pedido.id}/cambiar-estado/",
        {
            "estado_codigo": "EN_PRODUCCION",
        },
        format="json",
    )

    assert respuesta.status_code == 200

    pedido.refresh_from_db()
    assert pedido.estado.codigo == "EN_PRODUCCION"

    # 7. EN_PRODUCCION -> LISTO_ENTREGA vía API.
    respuesta = cliente.post(
        f"/api/v1/pedidos/{pedido.id}/cambiar-estado/",
        {
            "estado_codigo": "LISTO_ENTREGA",
        },
        format="json",
    )

    assert respuesta.status_code == 200

    pedido.refresh_from_db()
    assert pedido.estado.codigo == "LISTO_ENTREGA"

    # 8. Nota de entrega vía API.
    respuesta = cliente.post(
        f"/api/v1/pedidos/{pedido.id}/emitir_nota_entrega/",
        format="json",
    )

    assert respuesta.status_code == 201

    nota = NotaEntrega.objects.get(
        id=respuesta.data["id"],
    )

    assert nota.pedido_id == pedido.id
    assert nota.vendedor_id == actor.id

    # =========================================================
    # SEGUNDO RECORRIDO: CANCELACIÓN VÁLIDA SIN RECIBO EMITIDO
    # =========================================================

    cliente_cancelacion_id = crear_cliente_api(
        cliente,
        sufijo=" Cancelación",
    )

    pedido_cancelable = crear_proforma_api(
        cliente,
        cliente_id=cliente_cancelacion_id,
        producto=producto_cancelable,
    )

    producto_cancelable.refresh_from_db()

    assert pedido_cancelable.estado.codigo == "CONFIRMADO"
    assert producto_cancelable.stock == 0

    venta_cancelable = MovimientoStock.objects.get(
        pedido=pedido_cancelable,
        tipo_movimiento=valor(
            "TIPO_MOVIMIENTO",
            "VENTA",
        ),
    )

    orden_cancelable = OrdenTrabajo.objects.get(
        pedido=pedido_cancelable,
    )

    assert not Recibo.objects.filter(
        pedido=pedido_cancelable,
        estado="EMITIDO",
    ).exists()

    respuesta = cliente.post(
        f"/api/v1/pedidos/{pedido_cancelable.id}/cancelar/",
        format="json",
    )

    assert respuesta.status_code == 200

    pedido_cancelable.refresh_from_db()
    producto_cancelable.refresh_from_db()
    orden_cancelable.refresh_from_db()

    assert pedido_cancelable.estado.codigo == "CANCELADO"
    assert producto_cancelable.stock == 1
    assert orden_cancelable.estado.codigo == "CANCELADA"

    reversa = MovimientoStock.objects.get(
        movimiento_referencia=venta_cancelable,
        tipo_movimiento=valor(
            "TIPO_MOVIMIENTO",
            "REVERSA_VENTA",
        ),
    )

    assert reversa.producto_id == producto_cancelable.id
    assert reversa.cantidad == 1
    assert reversa.pedido_id is None
