from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.ordenes_trabajo.models import OrdenTrabajo
from apps.pedidos.models import Pedido
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


def preparar_proforma_enviada(actor, producto):
    proforma = crear_proforma(
        actor=actor,
        cliente=cliente_persona(actor),
    )

    agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor(
            "TIPO_ITEM",
            "SILLA",
        ),
        producto_id=producto.id,
        nombre=producto.nombre,
        cantidad=1,
        unidad=valor(
            "UNIDAD_MEDIDA",
            "PIEZA",
        ),
        precio_unitario=Decimal("50.00"),
    )

    return enviar_proforma(
        proforma_id=proforma.id,
        actor=actor,
    )


@pytest.mark.django_db(transaction=True)
def test_api_aprobar_no_requiere_body_y_devuelve_pedido_confirmado(
    django_user_model,
):
    actor = vendedor(
        django_user_model.objects.create_user(
            username="api-aprobar",
        )
    )

    producto = silla(
        actor,
        sku="API-APROBAR",
    )

    cargar_stock(
        producto,
        actor,
        1,
    )

    proforma = preparar_proforma_enviada(
        actor,
        producto,
    )

    cliente = APIClient()
    cliente.force_authenticate(actor)

    respuesta = cliente.post(
        f"/api/v1/proformas/{proforma.id}/aprobar/",
        format="json",
    )

    assert respuesta.status_code == 200

    assert set(respuesta.data) == {
        "pedido_id",
        "estado",
    }

    assert respuesta.data["estado"] == "CONFIRMADO"

    assert Pedido.objects.filter(
        id=respuesta.data["pedido_id"],
        proforma=proforma,
    ).exists()


@pytest.mark.django_db(transaction=True)
def test_api_cancelar_no_requiere_body(
    django_user_model,
):
    actor = vendedor(
        django_user_model.objects.create_user(
            username="api-cancelar",
        )
    )

    producto = silla(
        actor,
        sku="API-CANCELAR",
    )

    cargar_stock(
        producto,
        actor,
        1,
    )

    proforma = preparar_proforma_enviada(
        actor,
        producto,
    )

    cliente = APIClient()
    cliente.force_authenticate(actor)

    aprobacion = cliente.post(
        f"/api/v1/proformas/{proforma.id}/aprobar/",
        format="json",
    )

    assert aprobacion.status_code == 200

    pedido_id = aprobacion.data["pedido_id"]

    respuesta = cliente.post(
        f"/api/v1/pedidos/{pedido_id}/cancelar/",
        format="json",
    )

    assert respuesta.status_code == 200

    pedido = Pedido.objects.get(
        id=pedido_id,
    )

    assert pedido.estado.codigo == "CANCELADO"


@pytest.mark.django_db(transaction=True)
def test_orden_trabajo_respeta_permisos_y_aislamiento(
    django_user_model,
):
    propietario = vendedor(
        django_user_model.objects.create_user(
            username="ot-propietario",
        )
    )

    ajeno = vendedor(
        django_user_model.objects.create_user(
            username="ot-ajeno",
        )
    )

    sin_rol = django_user_model.objects.create_user(
        username="ot-sin-rol",
    )

    administrador = django_user_model.objects.create_user(
        username="ot-admin",
        is_staff=True,
    )

    producto = silla(
        propietario,
        sku="OT-PERMISOS",
    )

    cargar_stock(
        producto,
        propietario,
        1,
    )

    proforma = preparar_proforma_enviada(
        propietario,
        producto,
    )

    cliente = APIClient()
    cliente.force_authenticate(propietario)

    aprobacion = cliente.post(
        f"/api/v1/proformas/{proforma.id}/aprobar/",
        format="json",
    )

    assert aprobacion.status_code == 200

    pedido = Pedido.objects.get(
        id=aprobacion.data["pedido_id"],
    )

    orden = OrdenTrabajo.objects.get(
        pedido=pedido,
    )

    # Sin rol comercial.
    cliente.force_authenticate(sin_rol)

    respuesta = cliente.get(f"/api/v1/ordenes-trabajo/{orden.id}/")

    assert respuesta.status_code == 403

    # Vendedor ajeno no puede ver la OT.
    cliente.force_authenticate(ajeno)

    respuesta = cliente.get(f"/api/v1/ordenes-trabajo/{orden.id}/")

    assert respuesta.status_code == 404

    # Propietario sí puede verla.
    cliente.force_authenticate(propietario)

    respuesta = cliente.get(f"/api/v1/ordenes-trabajo/{orden.id}/")

    assert respuesta.status_code == 200

    # Staff tiene acceso administrativo.
    cliente.force_authenticate(administrador)

    respuesta = cliente.get(f"/api/v1/ordenes-trabajo/{orden.id}/")

    assert respuesta.status_code == 200
