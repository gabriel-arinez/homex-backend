from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.movimientos_stock.models import MovimientoStock
from apps.notas_entrega.models import NotaEntrega
from apps.notas_entrega.services import emitir_nota
from apps.ordenes_trabajo.models import OrdenTrabajo
from apps.proformas.models import RegistroProcedenciaImportacion
from apps.recibos.models import Recibo
from apps.recibos.services import emitir_recibo
from tests.api.test_fe05_contrato_operaciones import avanzar_a_listo_entrega
from tests.factories import silla, valor, vendedor
from tests.integration.test_f074_cobros import crear_pedido_confirmado

TZ_LA_PAZ = ZoneInfo("America/La_Paz")


@pytest.mark.django_db(transaction=True)
def test_movimientos_stock_orden_descendente_fecha_e_id_sin_alterar_saldo(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="orden-stock-user"))
    producto = silla(actor, sku="ORD-STK-001")
    tipo_ajuste = valor("TIPO_MOVIMIENTO", "AJUSTE")

    t1 = datetime(2026, 10, 1, 9, 0, tzinfo=TZ_LA_PAZ)
    t2 = datetime(2026, 10, 2, 10, 30, tzinfo=TZ_LA_PAZ)
    t3 = datetime(2026, 10, 3, 14, 15, tzinfo=TZ_LA_PAZ)

    # Insertados en orden no cronológico y con registrado_en invertido respecto a fecha.
    # Primero garantizamos stock suficiente para permitir la salida de -1.
    m_oldest = MovimientoStock.objects.create(
        producto=producto,
        fecha=t1,
        registrado_en=timezone.now() + timedelta(days=10),
        tipo_movimiento=tipo_ajuste,
        cantidad=Decimal("5.0000"),
        motivo="REPOSICION",
        observaciones="Reposición inicial",
        created_by=actor,
    )
    m_mid_a = MovimientoStock.objects.create(
        producto=producto,
        fecha=t2,
        tipo_movimiento=tipo_ajuste,
        cantidad=Decimal("3.0000"),
        motivo="REPOSICION",
        observaciones="Reposición media",
        created_by=actor,
    )
    m_mid_b = MovimientoStock.objects.create(
        producto=producto,
        fecha=t2,
        tipo_movimiento=tipo_ajuste,
        cantidad=Decimal("-1.0000"),
        motivo="MERMA",
        observaciones="Merma media",
        created_by=actor,
    )
    m_newest = MovimientoStock.objects.create(
        producto=producto,
        fecha=t3,
        tipo_movimiento=tipo_ajuste,
        cantidad=Decimal("3.0000"),
        motivo="REPOSICION",
        observaciones="Reposición final",
        created_by=actor,
    )

    esperado = [m_newest.id, m_mid_b.id, m_mid_a.id, m_oldest.id]

    cliente = APIClient()
    cliente.force_authenticate(actor)

    res_general = cliente.get("/api/v1/movimientos-stock/")
    assert res_general.status_code == 200
    assert [r["id"] for r in res_general.data["results"][:4]] == esperado

    res_prod = cliente.get("/api/v1/movimientos-stock/", {"producto": producto.id})
    assert res_prod.status_code == 200
    assert [r["id"] for r in res_prod.data["results"]] == esperado

    res_rep_p1 = cliente.get(
        "/api/v1/movimientos-stock/reporte/",
        {"producto": producto.id, "page_size": 2, "page": 1},
    )
    res_rep_p2 = cliente.get(
        "/api/v1/movimientos-stock/reporte/",
        {"producto": producto.id, "page_size": 2, "page": 2},
    )
    assert res_rep_p1.status_code == 200
    assert res_rep_p2.status_code == 200
    assert res_rep_p1.data["saldo_reconstruible"] is True
    assert [r["id"] for r in res_rep_p1.data["results"]] == esperado[:2]
    assert [r["id"] for r in res_rep_p2.data["results"]] == esperado[2:]
    # Verificar saldos reconstruidos cronológicamente: t1(+5)=5, t2_a(+3)=8, t2_b(-1)=7, t3(+3)=10
    assert res_rep_p1.data["results"][0]["saldo_posterior"] == "10.0000"
    assert res_rep_p1.data["results"][1]["saldo_posterior"] == "7.0000"
    assert res_rep_p2.data["results"][0]["saldo_posterior"] == "8.0000"
    assert res_rep_p2.data["results"][1]["saldo_posterior"] == "5.0000"


@pytest.mark.django_db(transaction=True)
def test_fecha_hora_ot_nota_entrega_y_recibo_expone_nuevos_e_importados(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="fechas-actor"))
    pedido, _ = crear_pedido_confirmado(actor, sku="FECHA-001")

    ot = OrdenTrabajo.objects.get(pedido=pedido)
    assert ot.fecha_hora is not None

    recibo = emitir_recibo(
        pedido=pedido,
        nombre_completo="Cliente Fecha",
        monto_en_letras="Cien",
        concepto="Anticipo",
        tipo_pago=valor("TIPO_PAGO", "EFECTIVO"),
        pago_actual=Decimal("25.00"),
        actor=actor,
    )
    assert recibo.fecha_hora is not None

    avanzar_a_listo_entrega(pedido)
    nota = emitir_nota(pedido=pedido, actor=actor)
    assert nota.fecha_hora is not None

    cliente = APIClient()
    cliente.force_authenticate(actor)

    assert cliente.get(f"/api/v1/ordenes-trabajo/{ot.id}/").data["fecha_hora"] is not None
    assert cliente.get(f"/api/v1/recibos/{recibo.id}/").data["fecha_hora"] is not None
    assert cliente.get(f"/api/v1/notas-entrega/{nota.id}/").data["fecha_hora"] is not None

    # Simular registro histórico importado (fecha_hora=None + procedencia con fecha_hora_comercial)
    ts_import = datetime(2026, 9, 15, 16, 45, tzinfo=TZ_LA_PAZ)
    pedido_hist, _ = crear_pedido_confirmado(actor, sku="FECHA-HIST-001")
    ot_hist = OrdenTrabajo.objects.get(pedido=pedido_hist)
    OrdenTrabajo.objects.filter(pk=ot_hist.pk).update(fecha_hora=None)
    recibo_hist = Recibo.objects.create(
        numero=990001,
        pedido=pedido_hist,
        nombre_completo="Cliente Histórico",
        monto_en_letras="Veinticinco",
        concepto="Anticipo histórico",
        tipo_pago=valor("TIPO_PAGO", "EFECTIVO"),
        pago_actual=Decimal("25.00"),
        fecha=ts_import.date(),
        fecha_hora=None,
        created_by=actor,
        updated_by=actor,
    )
    avanzar_a_listo_entrega(pedido_hist)
    nota_hist = NotaEntrega.objects.create(
        pedido=pedido_hist,
        vendedor=actor,
        numero=990001,
        fecha=ts_import.date(),
        fecha_hora=None,
        created_by=actor,
        updated_by=actor,
    )

    for entidad, obj_id in [
        ("ORDEN_TRABAJO", ot_hist.id),
        ("NOTA_ENTREGA", nota_hist.id),
        ("RECIBO", recibo_hist.id),
    ]:
        RegistroProcedenciaImportacion.objects.create(
            perfil="ESCENARIO",
            entidad=entidad,
            source_id=f"src-{entidad}-{obj_id}",
            objeto_id=obj_id,
            naturaleza="SIMULADO_NO_RESULTADO_MEDIDO",
            payload_hash="0" * 64,
            fecha_hora_comercial=ts_import,
        )

    ot_res = next(
        r for r in cliente.get("/api/v1/ordenes-trabajo/").json() if r["id"] == ot_hist.id
    )
    ne_res = next(
        r for r in cliente.get("/api/v1/notas-entrega/").json() if r["id"] == nota_hist.id
    )
    rec_res = next(r for r in cliente.get("/api/v1/recibos/").json() if r["id"] == recibo_hist.id)
    assert datetime.fromisoformat(ot_res["fecha_hora"]) == ts_import
    assert datetime.fromisoformat(ne_res["fecha_hora"]) == ts_import
    assert datetime.fromisoformat(rec_res["fecha_hora"]) == ts_import

    # Registro histórico sin fecha_hora ni procedencia -> None (no inventar hora)
    RegistroProcedenciaImportacion.objects.all().delete()
    assert cliente.get(f"/api/v1/ordenes-trabajo/{ot_hist.id}/").data["fecha_hora"] is None
    assert cliente.get(f"/api/v1/notas-entrega/{nota_hist.id}/").data["fecha_hora"] is None
    assert cliente.get(f"/api/v1/recibos/{recibo_hist.id}/").data["fecha_hora"] is None
