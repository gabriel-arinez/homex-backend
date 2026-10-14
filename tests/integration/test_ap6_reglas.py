from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.db import close_old_connections
from rest_framework.test import APIClient

from apps.catalogo.models import FamiliaProducto, Producto, ProductoPiso
from apps.movimientos_stock.models import MovimientoStock
from apps.pedidos.services import aprobar_proforma, cambiar_estado_pedido, cancelar_pedido
from apps.proformas.models import EspecificacionMueble
from apps.proformas.services import (
    actualizar_detalle,
    agregar_detalle,
    crear_proforma,
    enviar_proforma,
    marcar_no_concretada,
    reabrir_proforma,
)
from tests.factories import cargar_stock, cliente_persona, valor, vendedor


def piso(actor, *, sku="AP6-PISO", stock=Decimal("20.0000")):
    producto = Producto.objects.create(
        categoria=valor("CATEGORIA_PRODUCTO", "PISO_FLOTANTE"),
        sku=sku,
        nombre="Piso AP6",
        precio_lista=Decimal("125.00"),
        stock=0,
        unidad_stock=valor("UNIDAD_MEDIDA", "M2"),
        created_by=actor,
        updated_by=actor,
    )
    ProductoPiso.objects.create(producto=producto, created_by=actor, updated_by=actor)
    cargar_stock(producto, actor, stock)
    return producto


def cotizacion_piso(actor, producto, cantidad=Decimal("12.5000")):
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "PISO_FLOTANTE"),
        producto_id=producto.id,
        nombre=producto.nombre,
        cantidad=cantidad,
        unidad=valor("UNIDAD_MEDIDA", "M2"),
        precio_unitario=Decimal("125.00"),
        descuento=Decimal("25.00"),
    )
    enviar_proforma(proforma_id=proforma.id, actor=actor)
    return proforma, detalle


@pytest.mark.django_db(transaction=True)
def test_ap6_piso_decimal_venta_y_reversa_exactas(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap6-piso"))
    producto = piso(actor)
    proforma, detalle = cotizacion_piso(actor, producto)
    detalle.refresh_from_db()
    assert detalle.total == Decimal("1537.50")
    pedido = aprobar_proforma(proforma_id=proforma.id, actor=actor)
    producto.refresh_from_db()
    venta = MovimientoStock.objects.get(pedido=pedido)
    assert venta.cantidad == Decimal("-12.5000")
    assert producto.stock == Decimal("7.5000")
    cancelar_pedido(pedido_id=pedido.id, actor=actor)
    producto.refresh_from_db()
    reversa = MovimientoStock.objects.get(movimiento_referencia=venta)
    assert reversa.cantidad == Decimal("12.5000")
    assert producto.stock == Decimal("20.0000")


@pytest.mark.django_db(transaction=True)
def test_ap6_unidades_enteras_y_m2_decimal(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap6-unidades"))
    proforma = crear_proforma(actor=actor)
    with pytest.raises(Exception):
        agregar_detalle(
            proforma_id=proforma.id,
            actor=actor,
            tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
            nombre="Juego fraccionado",
            cantidad=Decimal("1.5"),
            unidad=valor("UNIDAD_MEDIDA", "JUEGO"),
            precio_unitario=Decimal("10"),
        )


@pytest.mark.django_db(transaction=True)
def test_ap6_variante_unica_y_pendiente_bloquea_aprobacion(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap6-variante"))
    familia = FamiliaProducto.objects.create(codigo="SILLA-X", nombre="Silla X")
    producto = Producto.objects.create(
        familia=familia,
        categoria=valor("CATEGORIA_PRODUCTO", "OTRO"),
        sku="SILLA-X-NEGRA",
        nombre="Silla X negra",
        precio_lista=Decimal("100"),
        stock=0,
        unidad_stock=valor("UNIDAD_MEDIDA", "PIEZA"),
    )
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    datos = dict(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "OTRO"),
        producto_id=producto.id,
        familia_producto=familia,
        nombre=producto.nombre,
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("90"),
    )
    agregar_detalle(**datos)
    with pytest.raises(Exception):
        agregar_detalle(**datos)

    pendiente = crear_proforma(actor=actor, cliente=cliente_persona(actor, sufijo=" Pendiente"))
    agregar_detalle(
        proforma_id=pendiente.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "OTRO"),
        familia_producto=familia,
        nombre="Silla X por definir",
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("90"),
    )
    enviar_proforma(proforma_id=pendiente.id, actor=actor)
    with pytest.raises(Exception):
        aprobar_proforma(proforma_id=pendiente.id, actor=actor)


@pytest.mark.django_db(transaction=True)
def test_ap6_mueble_a_eleccion_y_rutas_pedido(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap6-mueble"))
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
        nombre="Escritorio",
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("500"),
    )
    EspecificacionMueble.objects.create(
        proforma_detalle=detalle,
        datos_tecnicos={
            "componentes": [{"nombre": "tablero", "color": "A elección"}],
            "descripcion_original": "Escritorio color a elección",
            "advertencias": ["color_pendiente"],
        },
    )
    enviar_proforma(proforma_id=proforma.id, actor=actor)
    pedido = aprobar_proforma(proforma_id=proforma.id, actor=actor)
    with pytest.raises(Exception):
        cambiar_estado_pedido(pedido_id=pedido.id, actor=actor, estado_codigo="LISTO_ENTREGA")
    cambiar_estado_pedido(pedido_id=pedido.id, actor=actor, estado_codigo="EN_PRODUCCION")


@pytest.mark.django_db(transaction=True)
def test_ap6_jefe_taller_ve_ot_sin_precio_catalogo(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap6-vendedor-ot"))
    producto = piso(actor, sku="AP6-OT-PISO")
    proforma, _ = cotizacion_piso(actor, producto, Decimal("1.5000"))
    pedido = aprobar_proforma(proforma_id=proforma.id, actor=actor)
    jefe = django_user_model.objects.create_user(username="ap6-jefe")
    grupo, _ = Group.objects.get_or_create(name="JEFE_TALLER")
    jefe.groups.add(grupo)
    api = APIClient()
    api.force_authenticate(jefe)
    respuesta = api.get(f"/api/v1/ordenes-trabajo/{pedido.ordentrabajo.id}/")
    assert respuesta.status_code == 200
    linea = respuesta.data["detalles"][0]
    assert linea["especificacion"] is None
    assert "precio_unitario" not in linea
    assert "total" not in linea


@pytest.mark.django_db(transaction=True)
def test_ap6_cancelacion_concurrente_no_duplica_reversa(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap6-cancelacion"))
    producto = piso(actor, sku="AP6-CONCURRENTE")
    proforma, _ = cotizacion_piso(actor, producto, Decimal("2.5000"))
    pedido = aprobar_proforma(proforma_id=proforma.id, actor=actor)

    def cancelar():
        close_old_connections()
        try:
            cancelar_pedido(pedido_id=pedido.id, actor=actor)
            return "ok"
        except Exception:
            return "rechazado"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = list(pool.map(lambda _: cancelar(), range(2)))
    assert resultados.count("ok") == 1
    assert MovimientoStock.objects.filter(movimiento_referencia__pedido=pedido).count() == 1


@pytest.mark.django_db(transaction=True)
def test_ap6_no_concretada_exige_reapertura_para_editar(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="ap6-reapertura"))
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
        nombre="Mesa a elección",
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("500"),
    )
    EspecificacionMueble.objects.create(
        proforma_detalle=detalle,
        datos_tecnicos={"componentes": [{"nombre": "mesa", "color": "A elección"}]},
    )
    enviar_proforma(proforma_id=proforma.id, actor=actor)
    marcar_no_concretada(proforma_id=proforma.id, actor=actor)
    with pytest.raises(Exception):
        actualizar_detalle(detalle_id=detalle.id, actor=actor, nombre="Cambio indebido")
    reabierta = reabrir_proforma(proforma_id=proforma.id, actor=actor)
    assert reabierta.estado.codigo == "EN_REVISION"
    actualizado = actualizar_detalle(detalle_id=detalle.id, actor=actor, nombre="Cambio válido")
    assert actualizado.nombre == "Cambio válido"
