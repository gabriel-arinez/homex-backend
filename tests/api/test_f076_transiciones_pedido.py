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
            "estado_codigo": "ENTREGADO",
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


@pytest.mark.django_db(transaction=True)
def test_jefe_taller_marca_listo_entrega_desde_ot_y_emite_nota_automatica(django_user_model):
    from django.contrib.auth.models import Group

    from apps.notas_entrega.models import NotaEntrega
    from apps.ordenes_trabajo.models import OrdenTrabajo

    vendedor_user = vendedor(
        django_user_model.objects.create_user(username="f076-vend-auto"),
    )
    taller_user = django_user_model.objects.create_user(username="f076-jefe-taller")
    grupo_taller, _ = Group.objects.get_or_create(name="JEFE_TALLER")
    taller_user.groups.add(grupo_taller)

    from apps.proformas.services import crear_especificacion

    # Agregar un mueble a medida para habilitar la transición CONFIRMADO -> EN_PRODUCCION
    proforma = crear_proforma(actor=vendedor_user, cliente=cliente_persona(vendedor_user))
    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=vendedor_user,
        tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
        nombre="Escritorio ejecutivo a medida",
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("450.00"),
    )
    crear_especificacion(
        detalle_id=detalle.id,
        actor=vendedor_user,
        tipo_mueble=valor("TIPO_MUEBLE", "ESCRITORIO"),
        datos_tecnicos={"componentes": [{"nombre": "Tablero", "material": "Melamina"}]},
    )
    enviar_proforma(proforma_id=proforma.id, actor=vendedor_user)
    pedido = aprobar_proforma(proforma_id=proforma.id, actor=vendedor_user)
    ot = OrdenTrabajo.objects.get(pedido=pedido)

    cli_vend = APIClient()
    cli_vend.force_authenticate(vendedor_user)
    r_prod = cli_vend.post(
        f"/api/v1/pedidos/{pedido.id}/cambiar-estado/",
        {"estado_codigo": "EN_PRODUCCION"},
        format="json",
    )
    assert r_prod.status_code == 200
    ot.refresh_from_db()
    assert ot.estado.codigo == "EN_PROCESO"

    cli_taller = APIClient()
    cli_taller.force_authenticate(taller_user)
    r_listo = cli_taller.post(f"/api/v1/ordenes-trabajo/{ot.id}/marcar-listo-entrega/")
    assert r_listo.status_code == 200
    assert r_listo.data["pedido_estado_codigo"] == "LISTO_ENTREGA"
    assert r_listo.data["estado_info"]["codigo"] == "TERMINADA"

    nota = NotaEntrega.objects.get(pedido=pedido)
    assert nota.vendedor_id == vendedor_user.id
    assert nota.created_by_id == taller_user.id
