from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.notas_entrega.services import emitir_nota
from apps.ordenes_trabajo.models import OrdenTrabajo
from apps.recibos.services import emitir_recibo
from tests.factories import valor, vendedor
from tests.integration.test_f074_cobros import crear_pedido_confirmado


def avanzar_a_listo_entrega(pedido):
    pedido.estado = valor("ESTADO_PEDIDO", "EN_PRODUCCION")
    pedido.save(update_fields=["estado"])
    pedido.estado = valor("ESTADO_PEDIDO", "LISTO_ENTREGA")
    pedido.save(update_fields=["estado"])
    pedido.refresh_from_db()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "concepto",
    [
        "ESTADO_PEDIDO",
        "ESTADO_ORDEN_TRABAJO",
        "TIPO_PAGO",
        "TIPO_MOVIMIENTO",
    ],
)
def test_catalogos_operativos_fe05_son_publicos_para_vendedor(
    django_user_model,
    concepto,
):
    actor = vendedor(
        django_user_model.objects.create_user(
            username=f"fe05-catalogo-{concepto.lower()}",
        )
    )
    cliente = APIClient()
    cliente.force_authenticate(actor)

    respuesta = cliente.get(
        "/api/v1/catalogo/opciones/",
        {"concepto": concepto},
    )

    assert respuesta.status_code == 200
    assert respuesta.data
    assert all(item["concepto_codigo"] == concepto for item in respuesta.data)


@pytest.mark.django_db(transaction=True)
def test_movimientos_stock_publica_historial_read_only_con_filtros(
    django_user_model,
):
    actor = vendedor(
        django_user_model.objects.create_user(
            username="fe05-stock",
        )
    )
    pedido, proforma = crear_pedido_confirmado(
        actor,
        sku="FE05-STOCK",
    )
    producto = proforma.detalles.get().producto

    cliente = APIClient()
    cliente.force_authenticate(actor)

    respuesta = cliente.get(
        "/api/v1/movimientos-stock/",
        {
            "tipo_movimiento": "VENTA",
            "producto": producto.id,
            "pedido": pedido.id,
            "search": "FE05-STOCK",
        },
    )

    assert respuesta.status_code == 200
    assert respuesta.data["count"] == 1

    movimiento = respuesta.data["results"][0]
    assert movimiento["cantidad"] == -1
    assert movimiento["pedido"] == pedido.id
    assert movimiento["producto"] == producto.id
    assert movimiento["producto_resumen"] == {
        "id": producto.id,
        "sku": "FE05-STOCK",
        "nombre": producto.nombre,
    }
    assert movimiento["tipo_movimiento_info"]["codigo"] == "VENTA"

    assert cliente.post("/api/v1/movimientos-stock/", {}, format="json").status_code == 405
    assert (
        cliente.patch(
            f"/api/v1/movimientos-stock/{movimiento['id']}/",
            {"cantidad": 999},
            format="json",
        ).status_code
        == 405
    )
    assert cliente.delete(f"/api/v1/movimientos-stock/{movimiento['id']}/").status_code == 405


@pytest.mark.django_db(transaction=True)
def test_movimientos_stock_requiere_rol_comercial(
    django_user_model,
):
    sin_rol = django_user_model.objects.create_user(
        username="fe05-stock-sin-rol",
    )
    cliente = APIClient()
    cliente.force_authenticate(sin_rol)

    respuesta = cliente.get("/api/v1/movimientos-stock/")

    assert respuesta.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_detalle_ot_incluye_lineas_reales_de_la_proforma(
    django_user_model,
):
    actor = vendedor(
        django_user_model.objects.create_user(
            username="fe05-ot-detalle",
        )
    )
    pedido, proforma = crear_pedido_confirmado(
        actor,
        sku="FE05-OT-DETALLE",
    )
    orden = OrdenTrabajo.objects.get(pedido=pedido)

    cliente = APIClient()
    cliente.force_authenticate(actor)

    respuesta = cliente.get(f"/api/v1/ordenes-trabajo/{orden.id}/")

    assert respuesta.status_code == 200
    assert respuesta.data["proforma_numero"] == proforma.numero
    assert respuesta.data["estado_info"]["codigo"] == orden.estado.codigo
    assert len(respuesta.data["detalles"]) == 1
    assert respuesta.data["detalles"][0]["nombre"] == proforma.detalles.get().nombre
    assert respuesta.data["detalles"][0]["cantidad"] == 1


@pytest.mark.django_db(transaction=True)
def test_documentos_comerciales_son_descargables_y_respetan_aislamiento(
    django_user_model,
):
    propietario = vendedor(
        django_user_model.objects.create_user(
            username="fe05-documentos-propietario",
        )
    )
    ajeno = vendedor(
        django_user_model.objects.create_user(
            username="fe05-documentos-ajeno",
        )
    )

    pedido, proforma = crear_pedido_confirmado(
        propietario,
        sku="FE05-DOCUMENTOS",
    )
    orden = OrdenTrabajo.objects.get(pedido=pedido)
    recibo = emitir_recibo(
        pedido=pedido,
        actor=propietario,
        nombre_completo="Ana López",
        monto_en_letras="diez bolivianos",
        concepto="Anticipo",
        tipo_pago=valor("TIPO_PAGO", "EFECTIVO"),
        pago_actual=Decimal("10.00"),
    )
    avanzar_a_listo_entrega(pedido)
    nota = emitir_nota(
        pedido=pedido,
        actor=propietario,
    )

    recursos = [
        (
            f"/api/v1/proformas/{proforma.id}/documento/",
            f"proforma-{proforma.numero}.html",
            str(proforma.numero),
        ),
        (
            f"/api/v1/ordenes-trabajo/{orden.id}/documento/",
            f"orden-trabajo-{orden.numero}.html",
            str(orden.numero),
        ),
        (
            f"/api/v1/recibos/{recibo.id}/documento/",
            f"recibo-{recibo.numero}.html",
            str(recibo.numero),
        ),
        (
            f"/api/v1/notas-entrega/{nota.id}/documento/",
            f"nota-entrega-{nota.numero}.html",
            str(nota.numero),
        ),
    ]

    cliente = APIClient()
    cliente.force_authenticate(propietario)

    for url, nombre, evidencia in recursos:
        respuesta = cliente.get(url)
        assert respuesta.status_code == 200
        assert respuesta["Content-Type"].startswith("text/html")
        assert respuesta["Content-Disposition"] == f'attachment; filename="{nombre}"'
        assert evidencia in respuesta.content.decode()

    cliente.force_authenticate(ajeno)

    for url, _, _ in recursos:
        assert cliente.get(url).status_code == 404
