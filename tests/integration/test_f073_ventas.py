from decimal import Decimal
from threading import Barrier, Thread

import pytest
from django.db import DatabaseError, close_old_connections
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.movimientos_stock.models import MovimientoStock
from apps.ordenes_trabajo.models import OrdenTrabajo
from apps.pedidos.models import Pedido
from apps.pedidos.services import aprobar_proforma, cancelar_pedido
from apps.proformas.services import agregar_detalle, crear_proforma, enviar_proforma
from tests.factories import cargar_stock, cliente_persona, silla, valor


def proforma_enviada(
    actor,
    producto,
    cantidad=1,
):
    proforma = crear_proforma(
        actor=actor,
        cliente=cliente_persona(actor),
    )

    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "SILLA"),
        producto_id=producto.id,
        nombre=producto.nombre,
        cantidad=cantidad,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("50.00"),
    )

    return (
        enviar_proforma(
            proforma_id=proforma.id,
            actor=actor,
        ),
        detalle,
    )


def ejecutar_en_paralelo(operaciones):
    """
    Ejecuta operaciones simultáneamente con conexiones Django independientes.

    Barrier obliga a que todos los hilos estén listos antes de comenzar
    el caso de uso que se quiere someter a concurrencia.
    """
    barrera = Barrier(len(operaciones) + 1)
    resultados = []
    hilos = []

    def ejecutar(nombre, operacion):
        close_old_connections()

        try:
            barrera.wait(timeout=5)
            resultado = operacion()
        except Exception as exc:
            resultados.append(
                (
                    nombre,
                    "error",
                    exc,
                )
            )
        else:
            resultados.append(
                (
                    nombre,
                    "ok",
                    resultado,
                )
            )
        finally:
            close_old_connections()

    for nombre, operacion in operaciones:
        hilo = Thread(
            target=ejecutar,
            args=(
                nombre,
                operacion,
            ),
            daemon=True,
        )
        hilo.start()
        hilos.append(hilo)

    barrera.wait(timeout=5)

    for hilo in hilos:
        hilo.join(timeout=10)

    assert not any(hilo.is_alive() for hilo in hilos), "Una operación concurrente quedó bloqueada."

    return resultados


@pytest.mark.django_db(transaction=True)
def test_aprobacion_crea_exactamente_pedido_venta_ot_y_descuenta_stock(
    django_user_model,
):
    actor = django_user_model.objects.create_user(username="venta-ok")

    producto = silla(
        actor,
        sku="VENTA-OK",
    )

    cargar_stock(
        producto,
        actor,
        3,
    )

    proforma, _ = proforma_enviada(
        actor,
        producto,
        2,
    )

    pedido = aprobar_proforma(
        proforma_id=proforma.id,
        actor=actor,
    )

    producto.refresh_from_db()
    proforma.refresh_from_db()

    tipo_venta = valor(
        "TIPO_MOVIMIENTO",
        "VENTA",
    )

    assert proforma.estado.codigo == "APROBADA"

    assert Pedido.objects.filter(proforma=proforma).count() == 1

    assert (
        MovimientoStock.objects.filter(
            pedido=pedido,
            tipo_movimiento=tipo_venta,
            cantidad=-2,
        ).count()
        == 1
    )

    assert OrdenTrabajo.objects.filter(pedido=pedido).count() == 1

    assert producto.stock == 1


@pytest.mark.django_db(transaction=True)
def test_stock_insuficiente_hace_rollback_total_sin_efectos_parciales(
    django_user_model,
):
    actor = django_user_model.objects.create_user(username="venta-sin-stock")

    producto = silla(
        actor,
        sku="VENTA-SIN-STOCK",
    )

    cargar_stock(
        producto,
        actor,
        1,
    )

    proforma, _ = proforma_enviada(
        actor,
        producto,
        2,
    )

    with pytest.raises(ValidationError):
        aprobar_proforma(
            proforma_id=proforma.id,
            actor=actor,
        )

    proforma.refresh_from_db()
    producto.refresh_from_db()

    assert proforma.estado.codigo == "ENVIADA"
    assert producto.stock == 1

    assert not Pedido.objects.filter(proforma=proforma).exists()

    assert not MovimientoStock.objects.filter(pedido__proforma=proforma).exists()

    assert not OrdenTrabajo.objects.filter(pedido__proforma=proforma).exists()


@pytest.mark.django_db(transaction=True)
def test_aprobacion_doble_no_duplica_pedido_venta_ni_ot(
    django_user_model,
):
    actor = django_user_model.objects.create_user(username="venta-doble")

    producto = silla(
        actor,
        sku="VENTA-DOBLE",
    )

    cargar_stock(
        producto,
        actor,
        2,
    )

    proforma, _ = proforma_enviada(
        actor,
        producto,
    )

    pedido = aprobar_proforma(
        proforma_id=proforma.id,
        actor=actor,
    )

    with pytest.raises(ValidationError):
        aprobar_proforma(
            proforma_id=proforma.id,
            actor=actor,
        )

    producto.refresh_from_db()

    tipo_venta = valor(
        "TIPO_MOVIMIENTO",
        "VENTA",
    )

    assert Pedido.objects.filter(proforma=proforma).count() == 1

    assert (
        MovimientoStock.objects.filter(
            pedido=pedido,
            tipo_movimiento=tipo_venta,
        ).count()
        == 1
    )

    assert OrdenTrabajo.objects.filter(pedido=pedido).count() == 1

    assert producto.stock == 1


@pytest.mark.django_db(transaction=True)
def test_transicion_de_pedido_no_permitida_es_rechazada(
    django_user_model,
):
    actor = django_user_model.objects.create_user(username="transicion-invalida")

    producto = silla(
        actor,
        sku="TRANSICION-INVALIDA",
    )

    cargar_stock(
        producto,
        actor,
        1,
    )

    proforma, _ = proforma_enviada(
        actor,
        producto,
    )

    pedido = aprobar_proforma(
        proforma_id=proforma.id,
        actor=actor,
    )

    pedido.estado = valor(
        "ESTADO_PEDIDO",
        "ENTREGADO",
    )

    with pytest.raises(DatabaseError):
        pedido.save(update_fields=["estado"])

    pedido.refresh_from_db()

    assert pedido.estado.codigo == "CONFIRMADO"


@pytest.mark.django_db(transaction=True)
def test_t05_reversa_directa_rechazada_si_pedido_no_esta_cancelado(
    django_user_model,
):
    actor = django_user_model.objects.create_user(username="reversa-directa")

    producto = silla(
        actor,
        sku="REVERSA-DIRECTA",
    )

    cargar_stock(
        producto,
        actor,
        1,
    )

    proforma, _ = proforma_enviada(
        actor,
        producto,
    )

    pedido = aprobar_proforma(
        proforma_id=proforma.id,
        actor=actor,
    )

    tipo_venta = valor(
        "TIPO_MOVIMIENTO",
        "VENTA",
    )

    tipo_reversa = valor(
        "TIPO_MOVIMIENTO",
        "REVERSA_VENTA",
    )

    venta = MovimientoStock.objects.get(
        pedido=pedido,
        tipo_movimiento=tipo_venta,
    )

    with pytest.raises(DatabaseError):
        MovimientoStock.objects.create(
            producto=producto,
            tipo_movimiento=tipo_reversa,
            cantidad=1,
            movimiento_referencia=venta,
            fecha=timezone.now(),
            created_by=actor,
        )

    producto.refresh_from_db()

    assert producto.stock == 0

    assert not MovimientoStock.objects.filter(
        movimiento_referencia=venta,
        tipo_movimiento=tipo_reversa,
    ).exists()


@pytest.mark.django_db(transaction=True)
def test_cancelacion_crea_una_reversa_restituye_stock_y_cancela_ot(
    django_user_model,
):
    actor = django_user_model.objects.create_user(username="venta-cancelar")

    producto = silla(
        actor,
        sku="VENTA-CANCELAR",
    )

    cargar_stock(
        producto,
        actor,
        1,
    )

    proforma, _ = proforma_enviada(
        actor,
        producto,
    )

    pedido = aprobar_proforma(
        proforma_id=proforma.id,
        actor=actor,
    )

    tipo_venta = valor(
        "TIPO_MOVIMIENTO",
        "VENTA",
    )

    tipo_reversa = valor(
        "TIPO_MOVIMIENTO",
        "REVERSA_VENTA",
    )

    venta = MovimientoStock.objects.get(
        pedido=pedido,
        tipo_movimiento=tipo_venta,
    )

    cancelar_pedido(
        pedido_id=pedido.id,
        actor=actor,
    )

    pedido.refresh_from_db()
    producto.refresh_from_db()

    orden = OrdenTrabajo.objects.get(pedido=pedido)
    orden.refresh_from_db()

    assert pedido.estado.codigo == "CANCELADO"
    assert producto.stock == 1
    assert orden.estado.codigo == "CANCELADA"

    assert (
        MovimientoStock.objects.filter(
            movimiento_referencia=venta,
            tipo_movimiento=tipo_reversa,
        ).count()
        == 1
    )

    with pytest.raises(ValidationError):
        cancelar_pedido(
            pedido_id=pedido.id,
            actor=actor,
        )

    assert (
        MovimientoStock.objects.filter(
            movimiento_referencia=venta,
            tipo_movimiento=tipo_reversa,
        ).count()
        == 1
    )


@pytest.mark.concurrency
@pytest.mark.django_db(transaction=True)
def test_dos_aprobaciones_compiten_realmente_por_ultima_unidad(
    django_user_model,
):
    actor_uno = django_user_model.objects.create_user(username="competidor-uno")

    actor_dos = django_user_model.objects.create_user(username="competidor-dos")

    producto = silla(
        actor_uno,
        sku="ULTIMA-UNIDAD",
    )

    cargar_stock(
        producto,
        actor_uno,
        1,
    )

    primera, _ = proforma_enviada(
        actor_uno,
        producto,
    )

    segunda, _ = proforma_enviada(
        actor_dos,
        producto,
    )

    resultados = ejecutar_en_paralelo(
        [
            (
                "primera",
                lambda: aprobar_proforma(
                    proforma_id=primera.id,
                    actor=actor_uno,
                ),
            ),
            (
                "segunda",
                lambda: aprobar_proforma(
                    proforma_id=segunda.id,
                    actor=actor_dos,
                ),
            ),
        ]
    )

    exitos = [resultado for resultado in resultados if resultado[1] == "ok"]

    errores = [resultado for resultado in resultados if resultado[1] == "error"]

    assert len(exitos) == 1
    assert len(errores) == 1
    assert isinstance(
        errores[0][2],
        ValidationError,
    )

    producto.refresh_from_db()
    primera.refresh_from_db()
    segunda.refresh_from_db()

    assert sorted(
        [
            primera.estado.codigo,
            segunda.estado.codigo,
        ]
    ) == [
        "APROBADA",
        "ENVIADA",
    ]

    assert producto.stock == 0

    assert (
        Pedido.objects.filter(
            proforma__in=[
                primera,
                segunda,
            ]
        ).count()
        == 1
    )

    assert (
        MovimientoStock.objects.filter(
            pedido__proforma__in=[
                primera,
                segunda,
            ],
            tipo_movimiento=valor(
                "TIPO_MOVIMIENTO",
                "VENTA",
            ),
        ).count()
        == 1
    )

    assert (
        OrdenTrabajo.objects.filter(
            pedido__proforma__in=[
                primera,
                segunda,
            ]
        ).count()
        == 1
    )


@pytest.mark.concurrency
@pytest.mark.django_db(transaction=True)
def test_t05_cancelaciones_concurrentes_generan_una_sola_reversa(
    django_user_model,
):
    actor = django_user_model.objects.create_user(username="cancelacion-concurrente")

    producto = silla(
        actor,
        sku="CANCELACION-CONCURRENTE",
    )

    cargar_stock(
        producto,
        actor,
        1,
    )

    proforma, _ = proforma_enviada(
        actor,
        producto,
    )

    pedido = aprobar_proforma(
        proforma_id=proforma.id,
        actor=actor,
    )

    tipo_venta = valor(
        "TIPO_MOVIMIENTO",
        "VENTA",
    )

    tipo_reversa = valor(
        "TIPO_MOVIMIENTO",
        "REVERSA_VENTA",
    )

    venta = MovimientoStock.objects.get(
        pedido=pedido,
        tipo_movimiento=tipo_venta,
    )

    resultados = ejecutar_en_paralelo(
        [
            (
                "cancelacion-uno",
                lambda: cancelar_pedido(
                    pedido_id=pedido.id,
                    actor=actor,
                ),
            ),
            (
                "cancelacion-dos",
                lambda: cancelar_pedido(
                    pedido_id=pedido.id,
                    actor=actor,
                ),
            ),
        ]
    )

    exitos = [resultado for resultado in resultados if resultado[1] == "ok"]

    errores = [resultado for resultado in resultados if resultado[1] == "error"]

    assert len(exitos) == 1
    assert len(errores) == 1
    assert isinstance(
        errores[0][2],
        ValidationError,
    )

    pedido.refresh_from_db()
    producto.refresh_from_db()

    assert pedido.estado.codigo == "CANCELADO"
    assert producto.stock == 1

    assert (
        MovimientoStock.objects.filter(
            movimiento_referencia=venta,
            tipo_movimiento=tipo_reversa,
        ).count()
        == 1
    )
