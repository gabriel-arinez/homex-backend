from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from django.contrib.auth.models import Group
from django.db import DatabaseError, close_old_connections, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.catalogo.importador import ErrorCatalogo, importar_catalogo
from apps.catalogo.models import (
    ConceptoCatalogo,
    DescuentoProducto,
    Producto,
    ProductoPiso,
    ProductoSilla,
    ValorCatalogo,
)
from apps.core.exceptions import ConflictoComercial
from apps.movimientos_stock.models import MovimientoStock
from apps.movimientos_stock.services import calcular_saldos_y_resumen, registrar_ajuste_stock
from apps.notas_entrega.models import NotaEntrega
from apps.pedidos.services import aprobar_proforma, cambiar_estado_pedido, cancelar_pedido
from apps.proformas.models import EspecificacionMueble
from apps.proformas.services import (
    agregar_detalle,
    crear_proforma,
    enviar_proforma,
)
from apps.recibos.services import emitir_recibo_idempotente
from tests.factories import cargar_stock, cliente_persona, valor, vendedor


def _admin(user_model, username="modalidad-admin"):
    user = user_model.objects.create_user(username=username, is_staff=True)
    grupo, _ = Group.objects.get_or_create(name="ADMINISTRADOR_COMERCIAL")
    user.groups.add(grupo)
    return user


def _jefe_taller(user_model, username="modalidad-taller"):
    user = user_model.objects.create_user(username=username)
    grupo, _ = Group.objects.get_or_create(name="JEFE_TALLER")
    user.groups.add(grupo)
    return user


def _crear_piso(
    actor,
    *,
    sku="PISO-BP-001",
    nombre="Piso Flotante Roble",
    precio=Decimal("160.00"),
    modalidad=Producto.MODALIDAD_BAJO_PEDIDO,
    stock=Decimal("0"),
):
    producto = Producto.objects.create(
        categoria=valor("CATEGORIA_PRODUCTO", "PISO_FLOTANTE"),
        sku=sku,
        nombre=nombre,
        precio_lista=precio,
        modalidad_abastecimiento=modalidad,
        stock=0,
        unidad_stock=valor("UNIDAD_MEDIDA", "M2"),
        created_by=actor,
        updated_by=actor,
    )
    ProductoPiso.objects.create(producto=producto, created_by=actor, updated_by=actor)
    if stock > 0:
        cargar_stock(producto, actor, stock)
        producto.refresh_from_db()
    return producto


def _crear_silla(
    actor,
    *,
    sku="SILLA-CS-001",
    nombre="Silla Ergonómica",
    precio=Decimal("750.00"),
    stock=Decimal("10"),
):
    producto = Producto.objects.create(
        categoria=valor("CATEGORIA_PRODUCTO", "SILLA"),
        sku=sku,
        nombre=nombre,
        precio_lista=precio,
        modalidad_abastecimiento=Producto.MODALIDAD_CON_STOCK,
        stock=0,
        unidad_stock=valor("UNIDAD_MEDIDA", "PIEZA"),
        created_by=actor,
        updated_by=actor,
    )
    ProductoSilla.objects.create(producto=producto, created_by=actor, updated_by=actor)
    if stock > 0:
        cargar_stock(producto, actor, stock)
        producto.refresh_from_db()
    return producto


def _marca_generica():
    concepto, _ = ConceptoCatalogo.objects.get_or_create(codigo="MARCA")
    marca, _ = ValorCatalogo.objects.get_or_create(
        concepto=concepto, codigo="GENERICA", defaults={"nombre": "Genérica"}
    )
    return marca


def _color_negro():
    concepto, _ = ConceptoCatalogo.objects.get_or_create(codigo="COLOR")
    color, _ = ValorCatalogo.objects.get_or_create(
        concepto=concepto, codigo="NEGRO", defaults={"nombre": "Negro"}
    )
    return color


@pytest.mark.django_db(transaction=True)
def test_api_modalidad_predeterminada_por_categoria_y_filtros(django_user_model):
    admin = _admin(django_user_model)
    marca = _marca_generica()
    color = _color_negro()

    client = APIClient()
    client.force_authenticate(user=admin)

    res_piso = client.post(
        "/api/v1/catalogo/productos/",
        {
            "categoria": valor("CATEGORIA_PRODUCTO", "PISO_FLOTANTE").id,
            "sku": "API-PISO-DEF",
            "nombre": "Piso API Default",
            "precio_lista": "180.00",
            "unidad_stock": valor("UNIDAD_MEDIDA", "M2").id,
            "piso": {"marca": marca.id, "espesor_mm": "8.00"},
        },
        format="json",
    )
    assert res_piso.status_code == 201, res_piso.data
    assert res_piso.data["modalidad_abastecimiento"] == "BAJO_PEDIDO"
    assert res_piso.data["estado_stock"] == "BAJO_PEDIDO"
    assert res_piso.data["disponibilidad_referencial"] is None

    res_silla = client.post(
        "/api/v1/catalogo/productos/",
        {
            "categoria": valor("CATEGORIA_PRODUCTO", "SILLA").id,
            "sku": "API-SILLA-DEF",
            "nombre": "Silla API Default",
            "precio_lista": "500.00",
            "unidad_stock": valor("UNIDAD_MEDIDA", "PIEZA").id,
            "silla": {"marca": marca.id, "color_primario": color.id},
        },
        format="json",
    )
    assert res_silla.status_code == 201, res_silla.data
    assert res_silla.data["modalidad_abastecimiento"] == "CON_STOCK"
    assert res_silla.data["estado_stock"] == "SIN_EXISTENCIAS"

    # Filtros: SIN_EXISTENCIAS no debe incluir BAJO_PEDIDO
    res_sin_stock = client.get("/api/v1/catalogo/productos/?estado_stock=SIN_EXISTENCIAS")
    assert res_sin_stock.status_code == 200
    skus_sin_stock = {item["sku"] for item in res_sin_stock.data["results"]}
    assert "API-SILLA-DEF" in skus_sin_stock
    assert "API-PISO-DEF" not in skus_sin_stock

    res_bajo_pedido = client.get("/api/v1/catalogo/productos/?estado_stock=BAJO_PEDIDO")
    assert res_bajo_pedido.status_code == 200
    skus_bp = {item["sku"] for item in res_bajo_pedido.data["results"]}
    assert "API-PISO-DEF" in skus_bp
    assert "API-SILLA-DEF" not in skus_bp


@pytest.mark.django_db(transaction=True)
def test_pedido_exclusivo_pisos_bajo_pedido_sin_stock_y_flujo_ot(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="vendedor-piso-bp"))
    taller = _jefe_taller(django_user_model)
    piso = _crear_piso(actor, sku="PISO-SIN-STOCK", stock=Decimal("0"))

    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "PISO_FLOTANTE"),
        producto_id=piso.id,
        nombre=piso.nombre,
        cantidad=Decimal("18.7500"),
        unidad=valor("UNIDAD_MEDIDA", "M2"),
        precio_unitario=Decimal("160.00"),
        descuento=Decimal("100.00"),
    )
    detalle.refresh_from_db()
    assert detalle.total == Decimal("2900.00")

    enviar_proforma(proforma_id=proforma.id, actor=actor)
    pedido = aprobar_proforma(proforma_id=proforma.id, actor=actor)
    assert pedido.estado.codigo == "CONFIRMADO"

    piso.refresh_from_db()
    assert piso.stock == Decimal("0")
    assert not MovimientoStock.objects.filter(pedido=pedido).exists()

    # No es mueble a medida: no debe poder pasar a EN_PRODUCCION ni aparecer al taller
    with pytest.raises(ValidationError):
        cambiar_estado_pedido(pedido_id=pedido.id, actor=actor, estado_codigo="EN_PRODUCCION")

    client_taller = APIClient()
    client_taller.force_authenticate(user=taller)
    res_ot = client_taller.get("/api/v1/ordenes-trabajo/")
    assert res_ot.status_code == 200
    assert len(res_ot.data) == 0

    pedido = cambiar_estado_pedido(pedido_id=pedido.id, actor=actor, estado_codigo="LISTO_ENTREGA")
    assert pedido.estado.codigo == "LISTO_ENTREGA"
    pedido = cambiar_estado_pedido(pedido_id=pedido.id, actor=actor, estado_codigo="ENTREGADO")
    assert pedido.estado.codigo == "ENTREGADO"


@pytest.mark.django_db(transaction=True)
def test_pedido_sillas_stock_suficiente_e_insuficiente(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="vendedor-silla-cs"))
    silla = _crear_silla(actor, sku="SILLA-LIMIT", stock=Decimal("4"))

    proforma_exceso = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    agregar_detalle(
        proforma_id=proforma_exceso.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "SILLA"),
        producto_id=silla.id,
        nombre=silla.nombre,
        cantidad=Decimal("5"),
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("750.00"),
    )
    enviar_proforma(proforma_id=proforma_exceso.id, actor=actor)
    with pytest.raises(ConflictoComercial):
        aprobar_proforma(proforma_id=proforma_exceso.id, actor=actor)

    proforma_ok = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    agregar_detalle(
        proforma_id=proforma_ok.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "SILLA"),
        producto_id=silla.id,
        nombre=silla.nombre,
        cantidad=Decimal("3"),
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("750.00"),
    )
    enviar_proforma(proforma_id=proforma_ok.id, actor=actor)
    pedido = aprobar_proforma(proforma_id=proforma_ok.id, actor=actor)

    silla.refresh_from_db()
    assert silla.stock == Decimal("1")
    assert MovimientoStock.objects.filter(pedido=pedido, producto=silla).count() == 1


@pytest.mark.django_db(transaction=True)
def test_pedido_mixto_sillas_y_pisos_descuenta_solo_con_stock_y_revierte_selectivo(
    django_user_model,
):
    actor = vendedor(django_user_model.objects.create_user(username="vendedor-mixto-sp"))
    silla = _crear_silla(actor, sku="MIX-SILLA-1", stock=Decimal("8"))
    piso = _crear_piso(actor, sku="MIX-PISO-1", stock=Decimal("0"))

    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "SILLA"),
        producto_id=silla.id,
        nombre=silla.nombre,
        cantidad=Decimal("2"),
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("750.00"),
    )
    agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "PISO_FLOTANTE"),
        producto_id=piso.id,
        nombre=piso.nombre,
        cantidad=Decimal("24.5000"),
        unidad=valor("UNIDAD_MEDIDA", "M2"),
        precio_unitario=Decimal("160.00"),
    )
    enviar_proforma(proforma_id=proforma.id, actor=actor)
    pedido = aprobar_proforma(proforma_id=proforma.id, actor=actor)

    silla.refresh_from_db()
    piso.refresh_from_db()
    assert silla.stock == Decimal("6")
    assert piso.stock == Decimal("0")

    ventas = MovimientoStock.objects.filter(pedido=pedido)
    assert ventas.count() == 1
    assert ventas.get().producto_id == silla.id
    assert ventas.get().cantidad == Decimal("-2")

    cancelar_pedido(pedido_id=pedido.id, actor=actor)
    silla.refresh_from_db()
    piso.refresh_from_db()
    assert silla.stock == Decimal("8")
    assert piso.stock == Decimal("0")
    assert MovimientoStock.objects.filter(
        movimiento_referencia=ventas.get(), tipo_movimiento__codigo="REVERSA_VENTA"
    ).exists()
    assert not MovimientoStock.objects.filter(producto=piso).exists()


@pytest.mark.django_db(transaction=True)
def test_pedido_mixto_mueble_silla_y_piso_conserva_fabricacion_y_entrega(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="vendedor-mixto-3"))
    taller = _jefe_taller(django_user_model, username="taller-mixto-3")
    silla = _crear_silla(actor, sku="MIX3-SILLA", stock=Decimal("5"))
    piso = _crear_piso(actor, sku="MIX3-PISO", stock=Decimal("0"))

    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    det_mueble = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
        nombre="Escritorio ejecutivo a medida",
        cantidad=Decimal("1"),
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("2500.00"),
    )
    EspecificacionMueble.objects.create(
        proforma_detalle=det_mueble,
        tipo_mueble=valor("TIPO_MUEBLE", "ESCRITORIO"),
        datos_tecnicos={"componentes": [{"nombre": "Tablero principal"}]},
    )
    agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "SILLA"),
        producto_id=silla.id,
        nombre=silla.nombre,
        cantidad=Decimal("2"),
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("750.00"),
    )
    agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "PISO_FLOTANTE"),
        producto_id=piso.id,
        nombre=piso.nombre,
        cantidad=Decimal("15.2500"),
        unidad=valor("UNIDAD_MEDIDA", "M2"),
        precio_unitario=Decimal("160.00"),
    )
    enviar_proforma(proforma_id=proforma.id, actor=actor)
    pedido = aprobar_proforma(proforma_id=proforma.id, actor=actor)

    silla.refresh_from_db()
    piso.refresh_from_db()
    assert silla.stock == Decimal("3")
    assert piso.stock == Decimal("0")

    # Con mueble a medida debe pasar por EN_PRODUCCION antes de LISTO_ENTREGA
    with pytest.raises(ValidationError):
        cambiar_estado_pedido(pedido_id=pedido.id, actor=actor, estado_codigo="LISTO_ENTREGA")

    client_taller = APIClient()
    client_taller.force_authenticate(user=taller)
    res_ot = client_taller.get("/api/v1/ordenes-trabajo/")
    assert res_ot.status_code == 200
    assert len(res_ot.data) == 1

    pedido = cambiar_estado_pedido(pedido_id=pedido.id, actor=actor, estado_codigo="EN_PRODUCCION")
    assert pedido.estado.codigo == "EN_PRODUCCION"
    pedido = cambiar_estado_pedido(pedido_id=pedido.id, actor=actor, estado_codigo="LISTO_ENTREGA")
    assert pedido.estado.codigo == "LISTO_ENTREGA"


@pytest.mark.django_db(transaction=True)
def test_promociones_recibos_y_nota_entrega_con_bajo_pedido(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="vendedor-promo-bp"))
    piso = _crear_piso(actor, sku="PISO-PROMO-BP", precio=Decimal("200.00"), stock=Decimal("0"))
    DescuentoProducto.objects.create(
        producto=piso,
        precio_antes=Decimal("200.00"),
        precio_ahora=Decimal("150.00"),
        activo=True,
        created_by=actor,
        updated_by=actor,
    )

    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "PISO_FLOTANTE"),
        producto_id=piso.id,
        nombre=piso.nombre,
        cantidad=Decimal("10.5000"),
        unidad=valor("UNIDAD_MEDIDA", "M2"),
    )
    detalle.refresh_from_db()
    assert detalle.precio_unitario == Decimal("150.00")
    assert detalle.precio_antes_snapshot == Decimal("200.00")
    assert detalle.precio_ahora_snapshot == Decimal("150.00")
    assert detalle.total == Decimal("1575.00")

    enviar_proforma(proforma_id=proforma.id, actor=actor)
    pedido = aprobar_proforma(proforma_id=proforma.id, actor=actor)

    recibo, replay = emitir_recibo_idempotente(
        pedido=pedido,
        actor=actor,
        nombre_completo="Cliente Piso",
        monto_en_letras="Mil quinientos setenta y cinco 00/100 bolivianos",
        concepto="Pago total piso bajo pedido",
        tipo_pago=valor("TIPO_PAGO", "EFECTIVO"),
        pago_actual=Decimal("1575.00"),
    )
    assert replay is False
    assert recibo.saldo == Decimal("0.00")

    cambiar_estado_pedido(pedido_id=pedido.id, actor=actor, estado_codigo="LISTO_ENTREGA")
    nota = NotaEntrega.objects.get(pedido=pedido)
    assert nota.pedido_id == pedido.id


@pytest.mark.django_db(transaction=True)
def test_movimientos_incompatibles_y_stock_minimo_rechazados_para_bajo_pedido(django_user_model):
    admin = _admin(django_user_model, username="admin-incompat")
    piso = _crear_piso(admin, sku="PISO-INCOMPAT", stock=Decimal("0"))

    with pytest.raises(ValidationError):
        registrar_ajuste_stock(
            producto_id=piso.id,
            tipo_operacion="ENTRADA",
            cantidad=Decimal("5.0000"),
            motivo="REPOSICION",
            observaciones="Intento incompatible",
            actor=admin,
            clave_idempotencia="11111111-1111-4111-8111-111111111111",
        )

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            MovimientoStock.objects.create(
                producto=piso,
                fecha=timezone.now(),
                tipo_movimiento=valor("TIPO_MOVIMIENTO", "CARGA_INICIAL"),
                cantidad=Decimal("10.0000"),
                observaciones="Carga directa inválida",
                created_by=admin,
            )

    client = APIClient()
    client.force_authenticate(user=admin)
    res_minimo = client.patch(
        f"/api/v1/catalogo/productos/{piso.id}/stock-minimo/",
        {"stock_minimo": "5.0000"},
        format="json",
    )
    assert res_minimo.status_code == 400

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            Producto.objects.filter(pk=piso.id).update(stock_minimo=Decimal("5.0000"))


@pytest.mark.django_db(transaction=True)
def test_cambio_modalidad_preserva_existencias_e_historial_y_reversa_venta_previa(
    django_user_model,
):
    admin = _admin(django_user_model, username="admin-cambio-mod")
    piso = _crear_piso(
        admin,
        sku="PISO-CAMBIO-MOD",
        modalidad=Producto.MODALIDAD_CON_STOCK,
        stock=Decimal("20.0000"),
    )
    piso.stock_minimo = Decimal("2.0000")
    piso.save(update_fields=["stock_minimo"])

    # Mientras tenga stock > 0 no puede pasar a BAJO_PEDIDO (ni por API ni en PostgreSQL)
    client = APIClient()
    client.force_authenticate(user=admin)
    detalle_con_stock = client.get(f"/api/v1/catalogo/productos/{piso.id}/").data
    res_bloqueado = client.patch(
        f"/api/v1/catalogo/productos/{piso.id}/",
        {"modalidad_abastecimiento": "BAJO_PEDIDO"},
        format="json",
        HTTP_IF_MATCH=detalle_con_stock["revision"],
    )
    assert res_bloqueado.status_code == 400

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            Producto.objects.filter(pk=piso.id).update(
                modalidad_abastecimiento=Producto.MODALIDAD_BAJO_PEDIDO,
                stock_minimo=None,
            )

    # Venta total de las 20 unidades dejando stock = 0
    proforma = crear_proforma(actor=admin, cliente=cliente_persona(admin))
    agregar_detalle(
        proforma_id=proforma.id,
        actor=admin,
        tipo_item=valor("TIPO_ITEM", "PISO_FLOTANTE"),
        producto_id=piso.id,
        nombre=piso.nombre,
        cantidad=Decimal("20.0000"),
        unidad=valor("UNIDAD_MEDIDA", "M2"),
        precio_unitario=Decimal("160.00"),
    )
    enviar_proforma(proforma_id=proforma.id, actor=admin)
    pedido = aprobar_proforma(proforma_id=proforma.id, actor=admin)
    piso.refresh_from_db()
    assert piso.stock == Decimal("0.0000")

    # Con stock = 0 sí puede cambiar a BAJO_PEDIDO; limpia stock_minimo y preserva historial
    detalle_prod = client.get(f"/api/v1/catalogo/productos/{piso.id}/").data
    res_patch = client.patch(
        f"/api/v1/catalogo/productos/{piso.id}/",
        {"modalidad_abastecimiento": "BAJO_PEDIDO"},
        format="json",
        HTTP_IF_MATCH=detalle_prod["revision"],
    )
    assert res_patch.status_code == 200, res_patch.data
    assert res_patch.data["modalidad_abastecimiento"] == "BAJO_PEDIDO"
    assert res_patch.data["estado_stock"] == "BAJO_PEDIDO"
    assert res_patch.data["stock_minimo"] is None
    assert res_patch.data["disponibilidad_referencial"] is None

    # Cancelar pedido previo: debe revertir la VENTA efectivamente realizada
    cancelar_pedido(pedido_id=pedido.id, actor=admin)
    piso.refresh_from_db()
    assert piso.stock == Decimal("20.0000")

    # Volver a CON_STOCK mantiene saldo e historial reconstruible
    detalle_prod2 = client.get(f"/api/v1/catalogo/productos/{piso.id}/").data
    res_patch2 = client.patch(
        f"/api/v1/catalogo/productos/{piso.id}/",
        {"modalidad_abastecimiento": "CON_STOCK"},
        format="json",
        HTTP_IF_MATCH=detalle_prod2["revision"],
    )
    assert res_patch2.status_code == 200
    calculo = calcular_saldos_y_resumen(
        MovimientoStock.objects.filter(producto_id=piso.id),
        producto_id=piso.id,
    )
    assert calculo["saldo_reconstruible"] is True
    assert calculo["resumen"]["stock_actual"] == "20.0000"


@pytest.mark.django_db(transaction=True)
def test_importador_modalidad_abastecimiento(django_user_model):
    admin = _admin(django_user_model, username="admin-import-mod")
    _ = _marca_generica()
    _ = _color_negro()

    resultado = importar_catalogo(
        datos={
            "schema_version": 1,
            "productos": [
                {
                    "sku": "IMP-PISO-BP",
                    "categoria": "PISO_FLOTANTE",
                    "nombre": "Piso Importado BP",
                    "unidad_stock": "M2",
                    "precio_lista": "155.00",
                    "stock_inicial": "0",
                    "ficha": {"marca": "GENERICA"},
                },
                {
                    "sku": "IMP-SILLA-CS",
                    "categoria": "SILLA",
                    "nombre": "Silla Importada CS",
                    "unidad_stock": "PIEZA",
                    "precio_lista": "620.00",
                    "stock_inicial": "4",
                    "ficha": {"marca": "GENERICA", "color_primario": "NEGRO"},
                },
            ],
        },
        actor=admin,
    )
    assert resultado.creados == 2
    assert (
        Producto.objects.get(sku="IMP-PISO-BP").modalidad_abastecimiento
        == Producto.MODALIDAD_BAJO_PEDIDO
    )
    assert (
        Producto.objects.get(sku="IMP-SILLA-CS").modalidad_abastecimiento
        == Producto.MODALIDAD_CON_STOCK
    )

    with pytest.raises(ErrorCatalogo):
        importar_catalogo(
            datos={
                "schema_version": 1,
                "productos": [
                    {
                        "sku": "IMP-PISO-ERR",
                        "categoria": "PISO_FLOTANTE",
                        "nombre": "Piso Inválido",
                        "unidad_stock": "M2",
                        "precio_lista": "155.00",
                        "stock_inicial": "5",
                        "modalidad_abastecimiento": "BAJO_PEDIDO",
                        "ficha": {"marca": "GENERICA"},
                    }
                ],
            },
            actor=admin,
        )


@pytest.mark.django_db(transaction=True)
@pytest.mark.concurrency
def test_concurrencia_cambio_modalidad_vs_ajuste_stock(django_user_model):
    admin = _admin(django_user_model, username="conc-modalidad-ajuste")
    piso = _crear_piso(
        admin,
        sku="CONC-MOD-AJUSTE",
        modalidad=Producto.MODALIDAD_CON_STOCK,
        stock=Decimal("0"),
    )
    barrera = Barrier(2)

    def cambiar_a_bajo_pedido():
        close_old_connections()
        try:
            with transaction.atomic():
                prod = Producto.objects.select_for_update().get(pk=piso.id)
                barrera.wait(timeout=5)
                if prod.stock > 0:
                    return "blocked_stock"
                prod.modalidad_abastecimiento = Producto.MODALIDAD_BAJO_PEDIDO
                prod.stock_minimo = None
                prod.save(update_fields=["modalidad_abastecimiento", "stock_minimo"])
                return "ok"
        except DatabaseError:
            return "db_error"
        finally:
            close_old_connections()

    def ajustar_entrada():
        close_old_connections()
        try:
            barrera.wait(timeout=5)
            registrar_ajuste_stock(
                producto_id=piso.id,
                tipo_operacion="ENTRADA",
                cantidad=Decimal("5.0000"),
                motivo="REPOSICION",
                observaciones="Entrada concurrente",
                actor=admin,
                clave_idempotencia=str(uuid4()),
            )
            return "ok"
        except (ValidationError, DatabaseError):
            return "rejected"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        f_mod = executor.submit(cambiar_a_bajo_pedido)
        f_aj = executor.submit(ajustar_entrada)
        res_mod = f_mod.result()
        res_aj = f_aj.result()

    piso.refresh_from_db()
    # Nunca debe quedar BAJO_PEDIDO con stock > 0
    if piso.modalidad_abastecimiento == Producto.MODALIDAD_BAJO_PEDIDO:
        assert piso.stock == Decimal("0")
        assert res_mod == "ok"
        assert res_aj == "rejected"
    else:
        assert piso.stock == Decimal("5.0000")
        assert res_aj == "ok"
        assert res_mod in {"blocked_stock", "db_error"}


@pytest.mark.django_db(transaction=True)
@pytest.mark.concurrency
def test_concurrencia_confirmacion_pedido_vs_cambio_modalidad(django_user_model):
    admin = _admin(django_user_model, username="conc-conf-mod")
    piso = _crear_piso(
        admin,
        sku="CONC-CONF-MOD",
        modalidad=Producto.MODALIDAD_CON_STOCK,
        stock=Decimal("5.0000"),
    )
    proforma = crear_proforma(actor=admin, cliente=cliente_persona(admin))
    agregar_detalle(
        proforma_id=proforma.id,
        actor=admin,
        tipo_item=valor("TIPO_ITEM", "PISO_FLOTANTE"),
        producto_id=piso.id,
        nombre=piso.nombre,
        cantidad=Decimal("5.0000"),
        unidad=valor("UNIDAD_MEDIDA", "M2"),
        precio_unitario=Decimal("160.00"),
    )
    enviar_proforma(proforma_id=proforma.id, actor=admin)
    barrera = Barrier(2)

    def confirmar():
        close_old_connections()
        try:
            barrera.wait(timeout=5)
            aprobar_proforma(proforma_id=proforma.id, actor=admin)
            return "ok"
        except (ConflictoComercial, DatabaseError):
            return "error"
        finally:
            close_old_connections()

    def cambiar_modalidad():
        close_old_connections()
        try:
            barrera.wait(timeout=5)
            with transaction.atomic():
                prod = Producto.objects.select_for_update().get(pk=piso.id)
                if prod.stock > 0:
                    return "blocked_stock"
                prod.modalidad_abastecimiento = Producto.MODALIDAD_BAJO_PEDIDO
                prod.stock_minimo = None
                prod.save(update_fields=["modalidad_abastecimiento", "stock_minimo"])
                return "ok"
        except DatabaseError:
            return "db_error"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        f_conf = executor.submit(confirmar)
        f_mod = executor.submit(cambiar_modalidad)
        res_conf = f_conf.result()
        res_mod = f_mod.result()

    assert res_conf == "ok"
    piso.refresh_from_db()
    assert piso.stock == Decimal("0.0000")
    assert (
        MovimientoStock.objects.filter(producto=piso, tipo_movimiento__codigo="VENTA").count() == 1
    )
    assert res_mod in {"ok", "blocked_stock"}
