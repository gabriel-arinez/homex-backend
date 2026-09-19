from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.notas_entrega.services import emitir_nota
from apps.recibos.services import emitir_recibo
from tests.factories import valor, vendedor
from tests.integration.test_f074_cobros import crear_pedido_confirmado


def payload_recibo(*, pago="10.00"):
    return {
        "nombre_completo": "Ana López",
        "monto_en_letras": "diez bolivianos",
        "concepto": "Anticipo",
        "tipo_pago": valor(
            "TIPO_PAGO",
            "EFECTIVO",
        ).id,
        "pago_actual": pago,
    }


def avanzar_a_listo_entrega(pedido):
    pedido.estado = valor(
        "ESTADO_PEDIDO",
        "EN_PRODUCCION",
    )
    pedido.save(
        update_fields=["estado"],
    )

    pedido.estado = valor(
        "ESTADO_PEDIDO",
        "LISTO_ENTREGA",
    )
    pedido.save(
        update_fields=["estado"],
    )

    pedido.refresh_from_db()

    return pedido


@pytest.mark.django_db(transaction=True)
def test_recibos_respetan_permisos_y_aislamiento(
    django_user_model,
):
    propietario = vendedor(
        django_user_model.objects.create_user(
            username="recibo-propietario",
        )
    )

    ajeno = vendedor(
        django_user_model.objects.create_user(
            username="recibo-ajeno",
        )
    )

    sin_rol = django_user_model.objects.create_user(
        username="recibo-sin-rol",
    )

    administrador = django_user_model.objects.create_user(
        username="recibo-admin",
        is_staff=True,
    )

    pedido, _ = crear_pedido_confirmado(
        propietario,
        sku="API-RECIBO-PERMISOS",
    )

    recibo = emitir_recibo(
        pedido=pedido,
        actor=propietario,
        nombre_completo="Ana",
        monto_en_letras="diez",
        concepto="Anticipo",
        tipo_pago=valor(
            "TIPO_PAGO",
            "EFECTIVO",
        ),
        pago_actual=Decimal("10.00"),
    )

    cliente = APIClient()

    cliente.force_authenticate(sin_rol)

    respuesta = cliente.get(f"/api/v1/recibos/{recibo.id}/")

    assert respuesta.status_code == 403

    cliente.force_authenticate(ajeno)

    respuesta = cliente.get(f"/api/v1/recibos/{recibo.id}/")

    assert respuesta.status_code == 404

    respuesta = cliente.post(
        f"/api/v1/recibos/{recibo.id}/anular/",
        format="json",
    )

    assert respuesta.status_code == 404

    cliente.force_authenticate(propietario)

    respuesta = cliente.get(f"/api/v1/recibos/{recibo.id}/")

    assert respuesta.status_code == 200

    cliente.force_authenticate(administrador)

    respuesta = cliente.get(f"/api/v1/recibos/{recibo.id}/")

    assert respuesta.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_notas_respetan_permisos_y_aislamiento(
    django_user_model,
):
    propietario = vendedor(
        django_user_model.objects.create_user(
            username="nota-propietario",
        )
    )

    ajeno = vendedor(
        django_user_model.objects.create_user(
            username="nota-ajeno",
        )
    )

    sin_rol = django_user_model.objects.create_user(
        username="nota-sin-rol",
    )

    administrador = django_user_model.objects.create_user(
        username="nota-admin",
        is_staff=True,
    )

    pedido, _ = crear_pedido_confirmado(
        propietario,
        sku="API-NOTA-PERMISOS",
    )

    avanzar_a_listo_entrega(
        pedido,
    )

    nota = emitir_nota(
        pedido=pedido,
        actor=propietario,
    )

    cliente = APIClient()

    cliente.force_authenticate(sin_rol)

    respuesta = cliente.get(f"/api/v1/notas-entrega/{nota.id}/")

    assert respuesta.status_code == 403

    cliente.force_authenticate(ajeno)

    respuesta = cliente.get(f"/api/v1/notas-entrega/{nota.id}/")

    assert respuesta.status_code == 404

    cliente.force_authenticate(propietario)

    respuesta = cliente.get(f"/api/v1/notas-entrega/{nota.id}/")

    assert respuesta.status_code == 200

    cliente.force_authenticate(administrador)

    respuesta = cliente.get(f"/api/v1/notas-entrega/{nota.id}/")

    assert respuesta.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_api_sobrepago_devuelve_400(
    django_user_model,
):
    actor = vendedor(
        django_user_model.objects.create_user(
            username="api-sobrepago",
        )
    )

    pedido, _ = crear_pedido_confirmado(
        actor,
        sku="API-SOBREPAGO",
    )

    cliente = APIClient()
    cliente.force_authenticate(actor)

    respuesta = cliente.post(
        f"/api/v1/pedidos/{pedido.id}/emitir_recibo/",
        data=payload_recibo(
            pago="60.00",
        ),
        format="json",
    )

    assert respuesta.status_code == 400
    assert "recibo" in respuesta.data


@pytest.mark.django_db(transaction=True)
def test_api_p27_cobro_fuera_de_confirmado_devuelve_400(
    django_user_model,
):
    actor = vendedor(
        django_user_model.objects.create_user(
            username="api-p27",
        )
    )

    pedido, _ = crear_pedido_confirmado(
        actor,
        sku="API-P27",
    )

    pedido.estado = valor(
        "ESTADO_PEDIDO",
        "EN_PRODUCCION",
    )
    pedido.save(
        update_fields=["estado"],
    )

    cliente = APIClient()
    cliente.force_authenticate(actor)

    respuesta = cliente.post(
        f"/api/v1/pedidos/{pedido.id}/emitir_recibo/",
        data=payload_recibo(),
        format="json",
    )

    assert respuesta.status_code == 400
    assert "recibo" in respuesta.data


@pytest.mark.django_db(transaction=True)
def test_api_nota_fuera_de_listo_entrega_devuelve_400(
    django_user_model,
):
    actor = vendedor(
        django_user_model.objects.create_user(
            username="api-nota-estado",
        )
    )

    pedido, _ = crear_pedido_confirmado(
        actor,
        sku="API-NOTA-ESTADO",
    )

    cliente = APIClient()
    cliente.force_authenticate(actor)

    respuesta = cliente.post(
        f"/api/v1/pedidos/{pedido.id}/emitir_nota_entrega/",
        format="json",
    )

    assert respuesta.status_code == 400
    assert "nota_entrega" in respuesta.data
