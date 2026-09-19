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


@pytest.mark.django_db
def test_catalogo_es_visible_para_vendedor_pero_escritura_es_administrativa(
    django_user_model,
):
    propietario = vendedor(
        django_user_model.objects.create_user(
            username="catalogo-propietario",
        )
    )
    otro_vendedor = vendedor(
        django_user_model.objects.create_user(
            username="catalogo-vendedor",
        )
    )
    sin_rol = django_user_model.objects.create_user(
        username="catalogo-sin-rol",
    )
    administrador = django_user_model.objects.create_user(
        username="catalogo-admin",
        is_staff=True,
    )

    producto = silla(
        propietario,
        sku="F076-CATALOGO",
    )

    cliente = APIClient()

    cliente.force_authenticate(sin_rol)
    assert cliente.get("/api/v1/catalogo/productos/").status_code == 403

    cliente.force_authenticate(otro_vendedor)

    respuesta = cliente.get(f"/api/v1/catalogo/productos/{producto.id}/")
    assert respuesta.status_code == 200

    respuesta = cliente.patch(
        f"/api/v1/catalogo/productos/{producto.id}/",
        {"nombre": "Cambio no permitido"},
        format="json",
    )
    assert respuesta.status_code == 403

    respuesta = cliente.get(f"/api/v1/catalogo/sillas/{producto.id}/")
    assert respuesta.status_code == 403

    cliente.force_authenticate(administrador)

    respuesta = cliente.patch(
        f"/api/v1/catalogo/productos/{producto.id}/",
        {"nombre": "Cambio administrativo"},
        format="json",
    )
    assert respuesta.status_code == 200

    producto.refresh_from_db()
    assert producto.nombre == "Cambio administrativo"

    respuesta = cliente.get(f"/api/v1/catalogo/sillas/{producto.id}/")
    assert respuesta.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_proforma_y_detalle_aislan_objetos_y_acciones_por_vendedor(
    django_user_model,
):
    propietario = vendedor(
        django_user_model.objects.create_user(
            username="proforma-propietario",
        )
    )
    ajeno = vendedor(
        django_user_model.objects.create_user(
            username="proforma-ajeno",
        )
    )
    sin_rol = django_user_model.objects.create_user(
        username="proforma-sin-rol",
    )
    administrador = django_user_model.objects.create_user(
        username="proforma-admin",
        is_staff=True,
    )

    producto = silla(
        propietario,
        sku="F076-PROFORMA",
    )

    proforma = crear_proforma(
        actor=propietario,
        cliente=cliente_persona(propietario),
    )

    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=propietario,
        tipo_item=valor("TIPO_ITEM", "SILLA"),
        producto_id=producto.id,
        nombre=producto.nombre,
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("50.00"),
    )

    cliente = APIClient()

    cliente.force_authenticate(sin_rol)
    assert cliente.get("/api/v1/proformas/").status_code == 403

    cliente.force_authenticate(ajeno)

    assert cliente.get(f"/api/v1/proformas/{proforma.id}/").status_code == 404

    assert (
        cliente.patch(
            f"/api/v1/proformas/{proforma.id}/",
            {"titulo": "Intento ajeno"},
            format="json",
        ).status_code
        == 404
    )

    assert (
        cliente.post(
            f"/api/v1/proformas/{proforma.id}/enviar/",
            format="json",
        ).status_code
        == 404
    )

    assert (
        cliente.patch(
            f"/api/v1/proformas-detalle/{detalle.id}/",
            {"cantidad": 2},
            format="json",
        ).status_code
        == 404
    )

    assert (
        cliente.post(
            f"/api/v1/proformas-detalle/{detalle.id}/especificacion/",
            {"schema_version": 1},
            format="json",
        ).status_code
        == 404
    )

    cliente.force_authenticate(propietario)
    assert cliente.get(f"/api/v1/proformas/{proforma.id}/").status_code == 200

    cliente.force_authenticate(administrador)
    assert cliente.get(f"/api/v1/proformas/{proforma.id}/").status_code == 200


@pytest.mark.django_db(transaction=True)
def test_pedido_y_acciones_aislan_objeto_por_vendedor(
    django_user_model,
):
    propietario = vendedor(
        django_user_model.objects.create_user(
            username="pedido-propietario",
        )
    )
    ajeno = vendedor(
        django_user_model.objects.create_user(
            username="pedido-ajeno",
        )
    )
    sin_rol = django_user_model.objects.create_user(
        username="pedido-sin-rol",
    )
    administrador = django_user_model.objects.create_user(
        username="pedido-admin",
        is_staff=True,
    )

    producto = silla(
        propietario,
        sku="F076-PEDIDO",
    )
    cargar_stock(
        producto,
        propietario,
        1,
    )

    proforma = crear_proforma(
        actor=propietario,
        cliente=cliente_persona(propietario),
    )

    agregar_detalle(
        proforma_id=proforma.id,
        actor=propietario,
        tipo_item=valor("TIPO_ITEM", "SILLA"),
        producto_id=producto.id,
        nombre=producto.nombre,
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("50.00"),
    )

    enviar_proforma(
        proforma_id=proforma.id,
        actor=propietario,
    )

    pedido = aprobar_proforma(
        proforma_id=proforma.id,
        actor=propietario,
    )

    cliente = APIClient()

    cliente.force_authenticate(sin_rol)
    assert cliente.get("/api/v1/pedidos/").status_code == 403

    cliente.force_authenticate(ajeno)

    assert cliente.get(f"/api/v1/pedidos/{pedido.id}/").status_code == 404

    assert (
        cliente.post(
            f"/api/v1/pedidos/{pedido.id}/cancelar/",
            format="json",
        ).status_code
        == 404
    )

    payload_recibo = {
        "nombre_completo": "Usuario ajeno",
        "monto_en_letras": "diez",
        "concepto": "Intento no autorizado",
        "tipo_pago": valor("TIPO_PAGO", "EFECTIVO").id,
        "pago_actual": "10.00",
    }

    assert (
        cliente.post(
            f"/api/v1/pedidos/{pedido.id}/emitir_recibo/",
            payload_recibo,
            format="json",
        ).status_code
        == 404
    )

    assert (
        cliente.post(
            f"/api/v1/pedidos/{pedido.id}/emitir_nota_entrega/",
            format="json",
        ).status_code
        == 404
    )

    cliente.force_authenticate(propietario)
    assert cliente.get(f"/api/v1/pedidos/{pedido.id}/").status_code == 200

    cliente.force_authenticate(administrador)
    assert cliente.get(f"/api/v1/pedidos/{pedido.id}/").status_code == 200
