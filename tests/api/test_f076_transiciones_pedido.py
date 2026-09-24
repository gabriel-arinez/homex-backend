from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.pedidos.services import aprobar_proforma
from apps.proformas.services import (
    agregar_detalle,
    crear_proforma,
    enviar_proforma,
)
from tests.factories import (
    cargar_stock,
    cliente_persona,
    silla,
    valor,
    vendedor,
)


def crear_pedido_confirmado(actor, *, sku):
    producto = silla(
        actor,
        sku=sku,
    )
    cargar_stock(
        producto,
        actor,
        1,
    )

    proforma = crear_proforma(
        actor=actor,
        cliente=cliente_persona(actor),
    )

    agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "SILLA"),
        producto_id=producto.id,
        nombre=producto.nombre,
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("50.00"),
    )

    enviar_proforma(
        proforma_id=proforma.id,
        actor=actor,
    )

    return aprobar_proforma(
        proforma_id=proforma.id,
        actor=actor,
    )


@pytest.mark.django_db(transaction=True)
def test_api_permite_recorrido_normal_hasta_listo_entrega(
    django_user_model,
):
    actor = vendedor(
        django_user_model.objects.create_user(
            username="estado-normal",
        )
    )

    pedido = crear_pedido_confirmado(
        actor,
        sku="F076-ESTADO-NORMAL",
    )

    cliente = APIClient()
    cliente.force_authenticate(actor)

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


@pytest.mark.django_db(transaction=True)
def test_postgresql_rechaza_salto_de_estado_no_configurado(
    django_user_model,
):
    actor = vendedor(
        django_user_model.objects.create_user(
            username="estado-invalido",
        )
    )

    pedido = crear_pedido_confirmado(
        actor,
        sku="F076-ESTADO-INVALIDO",
    )

    cliente = APIClient()
    cliente.force_authenticate(actor)

    respuesta = cliente.post(
        f"/api/v1/pedidos/{pedido.id}/cambiar-estado/",
        {
            "estado_codigo": "LISTO_ENTREGA",
        },
        format="json",
    )

    assert respuesta.status_code == 400
    assert "estado" in respuesta.data

    pedido.refresh_from_db()
    assert pedido.estado.codigo == "CONFIRMADO"


@pytest.mark.django_db(transaction=True)
def test_vendedor_no_puede_cambiar_estado_de_pedido_ajeno(
    django_user_model,
):
    propietario = vendedor(
        django_user_model.objects.create_user(
            username="estado-propietario",
        )
    )

    ajeno = vendedor(
        django_user_model.objects.create_user(
            username="estado-ajeno",
        )
    )

    pedido = crear_pedido_confirmado(
        propietario,
        sku="F076-ESTADO-AJENO",
    )

    cliente = APIClient()
    cliente.force_authenticate(ajeno)

    respuesta = cliente.post(
        f"/api/v1/pedidos/{pedido.id}/cambiar-estado/",
        {
            "estado_codigo": "EN_PRODUCCION",
        },
        format="json",
    )

    assert respuesta.status_code == 404

    pedido.refresh_from_db()
    assert pedido.estado.codigo == "CONFIRMADO"


@pytest.mark.django_db(transaction=True)
def test_cambiar_estado_no_admite_cancelacion_generica(
    django_user_model,
):
    actor = vendedor(
        django_user_model.objects.create_user(
            username="estado-cancelacion",
        )
    )

    pedido = crear_pedido_confirmado(
        actor,
        sku="F076-ESTADO-CANCELACION",
    )

    cliente = APIClient()
    cliente.force_authenticate(actor)

    respuesta = cliente.post(
        f"/api/v1/pedidos/{pedido.id}/cambiar-estado/",
        {
            "estado_codigo": "CANCELADO",
        },
        format="json",
    )

    assert respuesta.status_code == 400

    pedido.refresh_from_db()
    assert pedido.estado.codigo == "CONFIRMADO"
