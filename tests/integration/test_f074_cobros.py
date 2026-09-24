from decimal import Decimal

import pytest
from django.db import DatabaseError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.notas_entrega.models import NotaEntrega
from apps.notas_entrega.services import emitir_nota
from apps.ordenes_trabajo.models import OrdenTrabajo
from apps.pedidos.services import aprobar_proforma
from apps.recibos.models import Recibo
from apps.recibos.services import anular_recibo, emitir_recibo
from tests.factories import cargar_stock, silla, valor
from tests.integration.test_f073_ventas import proforma_enviada


def crear_pedido_confirmado(
    actor,
    *,
    sku,
    cantidad=1,
):
    producto = silla(
        actor,
        sku=sku,
    )

    cargar_stock(
        producto,
        actor,
        cantidad,
    )

    proforma, _ = proforma_enviada(
        actor,
        producto,
        cantidad,
    )

    pedido = aprobar_proforma(
        proforma_id=proforma.id,
        actor=actor,
    )

    return pedido, proforma


def emitir_efectivo(
    *,
    pedido,
    actor,
    pago,
    concepto="Anticipo",
):
    return emitir_recibo(
        pedido=pedido,
        actor=actor,
        nombre_completo="Ana López",
        monto_en_letras="monto de prueba",
        concepto=concepto,
        tipo_pago=valor(
            "TIPO_PAGO",
            "EFECTIVO",
        ),
        pago_actual=Decimal(pago),
    )


@pytest.mark.django_db(transaction=True)
def test_recibo_correcto_y_sobrepago_rechazado(
    django_user_model,
):
    actor = django_user_model.objects.create_user(
        username="recibo-correcto",
    )

    pedido, _ = crear_pedido_confirmado(
        actor,
        sku="RECIBO-CORRECTO",
    )

    recibo = emitir_efectivo(
        pedido=pedido,
        actor=actor,
        pago="20.00",
    )

    assert recibo.estado == "EMITIDO"
    assert recibo.total == Decimal("50.00")
    assert recibo.pago_actual == Decimal("20.00")
    assert recibo.a_cuenta == Decimal("20.00")
    assert recibo.saldo == Decimal("30.00")

    with pytest.raises(ValidationError):
        emitir_efectivo(
            pedido=pedido,
            actor=actor,
            pago="31.00",
        )

    assert (
        Recibo.objects.filter(
            pedido=pedido,
            estado="EMITIDO",
        ).count()
        == 1
    )


@pytest.mark.django_db(transaction=True)
def test_t06_anulacion_no_permite_modificar_evidencia_ni_trasladar_recibo(
    django_user_model,
):
    actor = django_user_model.objects.create_user(
        username="t06-inmutable",
    )

    pedido, _ = crear_pedido_confirmado(
        actor,
        sku="T06-ORIGEN",
    )

    otro_pedido, _ = crear_pedido_confirmado(
        actor,
        sku="T06-DESTINO",
    )

    recibo = emitir_efectivo(
        pedido=pedido,
        actor=actor,
        pago="20.00",
        concepto="Anticipo original",
    )

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            Recibo.objects.filter(
                pk=recibo.id,
            ).update(
                estado="ANULADO",
                concepto="Concepto manipulado",
            )

    recibo.refresh_from_db()

    assert recibo.estado == "EMITIDO"
    assert recibo.concepto == "Anticipo original"

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            Recibo.objects.filter(
                pk=recibo.id,
            ).update(
                estado="ANULADO",
                pedido=otro_pedido,
            )

    recibo.refresh_from_db()

    assert recibo.estado == "EMITIDO"
    assert recibo.pedido_id == pedido.id

    anular_recibo(
        recibo_id=recibo.id,
        actor=actor,
    )

    recibo.refresh_from_db()

    assert recibo.estado == "ANULADO"
    assert recibo.concepto == "Anticipo original"
    assert recibo.pedido_id == pedido.id

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            Recibo.objects.filter(
                pk=recibo.id,
            ).delete()


@pytest.mark.django_db(transaction=True)
def test_recibo_anulado_deja_de_sumar_en_acumulado(
    django_user_model,
):
    actor = django_user_model.objects.create_user(
        username="recibo-acumulado",
    )

    pedido, _ = crear_pedido_confirmado(
        actor,
        sku="RECIBO-ACUMULADO",
        cantidad=2,
    )

    primero = emitir_efectivo(
        pedido=pedido,
        actor=actor,
        pago="30.00",
    )

    segundo = emitir_efectivo(
        pedido=pedido,
        actor=actor,
        pago="20.00",
    )

    assert primero.a_cuenta == Decimal("30.00")
    assert segundo.a_cuenta == Decimal("50.00")
    assert segundo.saldo == Decimal("50.00")

    anular_recibo(
        recibo_id=segundo.id,
        actor=actor,
    )

    tercero = emitir_efectivo(
        pedido=pedido,
        actor=actor,
        pago="50.00",
    )

    assert tercero.total == Decimal("100.00")
    assert tercero.a_cuenta == Decimal("80.00")
    assert tercero.saldo == Decimal("20.00")

    assert (
        Recibo.objects.filter(
            pedido=pedido,
            estado="EMITIDO",
        ).count()
        == 2
    )

    assert (
        Recibo.objects.filter(
            pedido=pedido,
            estado="ANULADO",
        ).count()
        == 1
    )


@pytest.mark.django_db(transaction=True)
def test_p27_cobro_solo_sobre_pedido_confirmado(
    django_user_model,
):
    actor = django_user_model.objects.create_user(
        username="p27-confirmado",
    )

    pedido, _ = crear_pedido_confirmado(
        actor,
        sku="P27",
    )

    pedido.estado = valor(
        "ESTADO_PEDIDO",
        "EN_PRODUCCION",
    )

    pedido.save(
        update_fields=["estado"],
    )

    with pytest.raises(ValidationError):
        emitir_efectivo(
            pedido=pedido,
            actor=actor,
            pago="10.00",
        )

    assert not Recibo.objects.filter(
        pedido=pedido,
    ).exists()


@pytest.mark.django_db(transaction=True)
def test_tipo_pago_y_reglas_de_cheque_se_preservan(
    django_user_model,
):
    actor = django_user_model.objects.create_user(
        username="tipo-pago",
    )

    pedido, _ = crear_pedido_confirmado(
        actor,
        sku="TIPO-PAGO",
    )

    with pytest.raises(ValidationError):
        emitir_recibo(
            pedido=pedido,
            actor=actor,
            nombre_completo="Ana",
            monto_en_letras="diez",
            concepto="Tipo inválido",
            tipo_pago=valor(
                "MONEDA",
                "BOB",
            ),
            pago_actual=Decimal("10.00"),
        )

    with pytest.raises(ValidationError):
        emitir_recibo(
            pedido=pedido,
            actor=actor,
            nombre_completo="Ana",
            monto_en_letras="diez",
            concepto="Cheque incompleto",
            tipo_pago=valor(
                "TIPO_PAGO",
                "CHEQUE",
            ),
            pago_actual=Decimal("10.00"),
        )

    cheque = emitir_recibo(
        pedido=pedido,
        actor=actor,
        nombre_completo="Ana",
        monto_en_letras="diez",
        concepto="Cheque válido",
        tipo_pago=valor(
            "TIPO_PAGO",
            "CHEQUE",
        ),
        numero_cheque="CH-001",
        banco="Banco prueba",
        pago_actual=Decimal("10.00"),
    )

    assert cheque.numero_cheque == "CH-001"
    assert cheque.banco == "Banco prueba"


@pytest.mark.django_db(transaction=True)
def test_nota_solo_desde_listo_entrega_y_es_unica(
    django_user_model,
):
    actor = django_user_model.objects.create_user(
        username="nota-unica",
    )

    pedido, _ = crear_pedido_confirmado(
        actor,
        sku="NOTA-UNICA",
    )

    with pytest.raises(ValidationError):
        emitir_nota(
            pedido=pedido,
            actor=actor,
        )

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

    nota = emitir_nota(
        pedido=pedido,
        actor=actor,
    )

    assert nota.pedido_id == pedido.id
    assert nota.fecha == timezone.localdate()

    with pytest.raises(DatabaseError):
        emitir_nota(
            pedido=pedido,
            actor=actor,
        )

    assert (
        NotaEntrega.objects.filter(
            pedido=pedido,
        ).count()
        == 1
    )


@pytest.mark.django_db(transaction=True)
def test_servicios_rechazan_operar_pedido_de_otro_vendedor(
    django_user_model,
):
    propietario = django_user_model.objects.create_user(
        username="servicio-propietario",
    )

    ajeno = django_user_model.objects.create_user(
        username="servicio-ajeno",
    )

    pedido, _ = crear_pedido_confirmado(
        propietario,
        sku="SERVICIO-AJENO",
    )

    recibo = emitir_efectivo(
        pedido=pedido,
        actor=propietario,
        pago="10.00",
    )

    with pytest.raises(PermissionDenied):
        anular_recibo(
            recibo_id=recibo.id,
            actor=ajeno,
        )

    with pytest.raises(PermissionDenied):
        emitir_efectivo(
            pedido=pedido,
            actor=ajeno,
            pago="10.00",
        )

    recibo.refresh_from_db()

    assert recibo.estado == "EMITIDO"


@pytest.mark.django_db(transaction=True)
def test_documentos_renderizan_datos_persistidos(
    django_user_model,
):
    from apps.documentos.services import (
        renderizar_nota_entrega,
        renderizar_orden_trabajo,
        renderizar_proforma,
        renderizar_recibo,
    )

    actor = django_user_model.objects.create_user(
        username="documentos-f074",
    )

    pedido, proforma = crear_pedido_confirmado(
        actor,
        sku="DOCUMENTOS-F074",
    )

    recibo = emitir_efectivo(
        pedido=pedido,
        actor=actor,
        pago="20.00",
    )

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

    nota = emitir_nota(
        pedido=pedido,
        actor=actor,
    )

    orden = OrdenTrabajo.objects.get(
        pedido=pedido,
    )

    assert str(proforma.numero) in renderizar_proforma(proforma.id)

    assert str(orden.numero) in renderizar_orden_trabajo(orden.id)

    assert str(recibo.numero) in renderizar_recibo(recibo.id)

    assert str(nota.numero) in renderizar_nota_entrega(nota.id)
