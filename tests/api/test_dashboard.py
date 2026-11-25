from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.core.tiempo_comercial import reloj_comercial_simulado
from apps.ordenes_trabajo.models import HistorialEstadoOrdenTrabajo, OrdenTrabajo
from apps.ordenes_trabajo.services import cambiar_estado_orden_trabajo
from apps.pedidos.services import aprobar_proforma, cambiar_estado_pedido, cancelar_pedido
from apps.proformas.models import EspecificacionMueble
from apps.proformas.services import agregar_detalle, crear_proforma, enviar_proforma
from apps.recibos.services import anular_recibo, emitir_recibo
from tests.factories import cargar_stock, cliente_persona, encargado_tienda, silla, valor

TZ_LA_PAZ = ZoneInfo("America/La_Paz")
User = get_user_model()

ADMIN_ENDPOINTS = [
    "/api/v1/dashboard/administrador/",
    "/api/v1/dashboard/administrador/comercial/",
    "/api/v1/dashboard/administrador/finanzas/",
    "/api/v1/dashboard/administrador/inventario/",
]
TIENDA_ENDPOINTS = [
    "/api/v1/dashboard/tienda/",
    "/api/v1/dashboard/tienda/seguimiento/",
]
TALLER_ENDPOINTS = [
    "/api/v1/dashboard/taller/",
    "/api/v1/dashboard/taller/planificacion/",
]


def _crear_usuarios():
    admin = User.objects.create_user(
        username="admin_dash", password="x", is_staff=True, first_name="Ana", last_name="Admin"
    )
    v1 = encargado_tienda(
        User.objects.create_user(
            username="vend1_dash", password="x", first_name="Alvaro", last_name="V1"
        )
    )
    v2 = encargado_tienda(
        User.objects.create_user(
            username="vend2_dash", password="x", first_name="Rodrigo", last_name="V2"
        )
    )
    jefe = User.objects.create_user(
        username="taller_dash", password="x", first_name="Antonio", last_name="Taller"
    )
    grupo_taller, _ = Group.objects.get_or_create(name="JEFE_TALLER")
    jefe.groups.add(grupo_taller)
    return admin, v1, v2, jefe


def _autenticar(user) -> APIClient:
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _crear_proforma_mueble(
    *,
    vendedor,
    cliente,
    fecha: date,
    moneda="BOB",
    precio="1000.00",
    cantidad="1.0000",
    validez=10,
    formalizar=True,
    tipo_mueble_codigo="ESCRITORIO",
):
    dt = datetime(fecha.year, fecha.month, fecha.day, 10, 0, tzinfo=TZ_LA_PAZ)
    with reloj_comercial_simulado(fecha, fecha_hora=dt):
        prof = crear_proforma(
            actor=vendedor,
            cliente=cliente,
            moneda_codigo=moneda,
            validez_oferta=validez,
        )
        det = agregar_detalle(
            proforma_id=prof.id,
            actor=vendedor,
            tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
            nombre="Escritorio ejecutivo",
            cantidad=Decimal(cantidad),
            unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
            precio_unitario=Decimal(precio),
        )
        EspecificacionMueble.objects.create(
            proforma_detalle=det,
            tipo_mueble=valor("TIPO_MUEBLE", tipo_mueble_codigo),
            datos_tecnicos={"largo": 160},
        )
        if formalizar:
            enviar_proforma(proforma_id=prof.id, actor=vendedor)
        prof.refresh_from_db()
        return prof


def _crear_proforma_producto(
    *,
    vendedor,
    cliente,
    producto,
    fecha: date,
    moneda="BOB",
    precio="200.00",
    cantidad="2.0000",
    formalizar=True,
):
    dt = datetime(fecha.year, fecha.month, fecha.day, 11, 0, tzinfo=TZ_LA_PAZ)
    with reloj_comercial_simulado(fecha, fecha_hora=dt):
        prof = crear_proforma(
            actor=vendedor,
            cliente=cliente,
            moneda_codigo=moneda,
            validez_oferta=10,
        )
        agregar_detalle(
            proforma_id=prof.id,
            actor=vendedor,
            tipo_item=valor("TIPO_ITEM", "SILLA"),
            producto=producto,
            nombre=producto.nombre,
            cantidad=Decimal(cantidad),
            unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
            precio_unitario=Decimal(precio),
        )
        if formalizar:
            enviar_proforma(proforma_id=prof.id, actor=vendedor)
        prof.refresh_from_db()
        return prof


@pytest.mark.django_db
def test_permisos_y_aislamiento_perfiles():
    admin, v1, v2, jefe = _crear_usuarios()
    anon = APIClient()

    for url in ADMIN_ENDPOINTS + TIENDA_ENDPOINTS + TALLER_ENDPOINTS:
        assert anon.get(url).status_code == 401

    c_admin = _autenticar(admin)
    c_v1 = _autenticar(v1)
    c_jefe = _autenticar(jefe)

    for url in ADMIN_ENDPOINTS:
        assert c_admin.get(url).status_code == 200
        assert c_v1.get(url).status_code == 403
        assert c_jefe.get(url).status_code == 403

    for url in TIENDA_ENDPOINTS:
        assert c_v1.get(url).status_code == 200
        assert c_admin.get(url).status_code == 200
        assert c_jefe.get(url).status_code == 403

    for url in TALLER_ENDPOINTS:
        assert c_jefe.get(url).status_code == 200
        assert c_admin.get(url).status_code == 200
        assert c_v1.get(url).status_code == 403

    # Aislamiento estricto: un vendedor no puede consultar otro vendedor manipulando query params
    resp_tamper = c_v1.get(f"/api/v1/dashboard/tienda/?vendedor={v2.id}")
    assert resp_tamper.status_code == 403
    resp_self = c_v1.get(f"/api/v1/dashboard/tienda/?vendedor={v1.id}")
    assert resp_self.status_code == 200
    assert resp_self.json()["vendedor_id"] == v1.id


@pytest.mark.django_db
def test_ausencia_de_datos_y_division_por_cero():
    admin, v1, _, jefe = _crear_usuarios()

    resp_adm = _autenticar(admin).get(
        f"/api/v1/dashboard/administrador/?vendedor={v1.id}&fecha_desde=2099-01-01&fecha_hasta=2099-01-31"
    )
    assert resp_adm.status_code == 200
    data_adm = resp_adm.json()
    assert data_adm["comercial"]["total_proformas"] == 0
    assert data_adm["comercial"]["tasa_conversion_cohorte"] is None
    assert data_adm["finanzas"]["por_moneda"] == []
    assert data_adm["produccion"]["cumplimiento_entregas_porcentaje"] is None

    resp_tal = _autenticar(jefe).get(
        "/api/v1/dashboard/taller/?entrega_desde=2099-01-01&entrega_hasta=2099-01-31"
    )
    assert resp_tal.status_code == 200
    data_tal = resp_tal.json()
    assert data_tal["indicadores"]["tiempo_promedio_fabricacion_horas"] is None
    assert data_tal["indicadores"]["cumplimiento_entregas_porcentaje"] is None
    assert data_tal["cola_prioridades"]["total"] == 0


@pytest.mark.django_db
def test_conciliacion_financiera_recibos_anulados_pedidos_cancelados_y_no_duplicacion():
    admin, v1, v2, _ = _crear_usuarios()
    cli = cliente_persona(v1)
    prod = silla(admin, sku="S-DASH-1", precio="200.00", stock=0)
    cargar_stock(prod, admin, Decimal("20.0000"))

    f_oct = date(2026, 10, 10)
    # Proforma 1 (v1): 2 líneas (1 mueble 1000 + 2 sillas * 200 = 1400 BOB) -> Pedido con 2 recibos
    prof1 = _crear_proforma_mueble(
        vendedor=v1, cliente=cli, fecha=f_oct, precio="1000.00", cantidad="1.0000"
    )
    with reloj_comercial_simulado(f_oct):
        agregar_detalle(
            proforma_id=prof1.id,
            actor=v1,
            tipo_item=valor("TIPO_ITEM", "SILLA"),
            producto=prod,
            nombre=prod.nombre,
            cantidad=Decimal("2.0000"),
            unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
            precio_unitario=Decimal("200.00"),
        )
        ped1 = aprobar_proforma(proforma_id=prof1.id, actor=v1)
        emitir_recibo(
            pedido=ped1,
            actor=v1,
            nombre_completo="Ana López",
            monto_en_letras="Cuatrocientos 00/100",
            concepto="Adelanto 1",
            tipo_pago=valor("TIPO_PAGO", "EFECTIVO"),
            pago_actual=Decimal("400.00"),
        )
        rec_anulado = emitir_recibo(
            pedido=ped1,
            actor=v1,
            nombre_completo="Ana López",
            monto_en_letras="Cien 00/100",
            concepto="Error",
            tipo_pago=valor("TIPO_PAGO", "EFECTIVO"),
            pago_actual=Decimal("100.00"),
        )
        anular_recibo(recibo_id=rec_anulado.id, actor=v1)
        emitir_recibo(
            pedido=ped1,
            actor=v1,
            nombre_completo="Ana López",
            monto_en_letras="Seiscientos 00/100",
            concepto="Adelanto 2",
            tipo_pago=valor("TIPO_PAGO", "QR"),
            pago_actual=Decimal("600.00"),
        )

    # Proforma 2 (v2): 500 BOB -> Pedido CANCELADO (regla PG exige anular/sin cobros activos)
    prof2 = _crear_proforma_mueble(
        vendedor=v2, cliente=cli, fecha=f_oct, precio="500.00", cantidad="1.0000"
    )
    with reloj_comercial_simulado(f_oct):
        ped2 = aprobar_proforma(proforma_id=prof2.id, actor=v2)
        cancelar_pedido(pedido_id=ped2.id, actor=v2)

    # Proforma 3 (v2): borrador y Proforma 4 (v1): USD (no debe sumarse con BOB)
    _crear_proforma_mueble(vendedor=v2, cliente=cli, fecha=f_oct, precio="300.00", formalizar=False)
    prof_usd = _crear_proforma_mueble(
        vendedor=v1, cliente=cli, fecha=f_oct, moneda="USD", precio="500.00"
    )
    with reloj_comercial_simulado(f_oct):
        aprobar_proforma(proforma_id=prof_usd.id, actor=v1)

    c_admin = _autenticar(admin)
    resp = c_admin.get(
        "/api/v1/dashboard/administrador/finanzas/?fecha_desde=2026-10-10&fecha_hasta=2026-10-10"
    )
    assert resp.status_code == 200
    fin = resp.json()

    por_moneda = {x["moneda"]: x for x in fin["por_moneda"]}
    assert set(por_moneda.keys()) == {"BOB", "USD"}
    # BOB: solo ped1 (1400.00), cobrado 400 + 600 = 1000.00 (anulado y cancelado excluidos)
    assert Decimal(str(por_moneda["BOB"]["importe_pedidos_no_cancelados"])) == Decimal("1400.00")
    assert Decimal(str(por_moneda["BOB"]["cobros_acumulados_cartera_vigente"])) == Decimal(
        "1000.00"
    )
    assert Decimal(str(por_moneda["BOB"]["saldo_pendiente"])) == Decimal("400.00")
    # USD separado: 500.00
    assert Decimal(str(por_moneda["USD"]["importe_pedidos_no_cancelados"])) == Decimal("500.00")
    assert Decimal(str(por_moneda["USD"]["saldo_pendiente"])) == Decimal("500.00")
    assert fin["cobros_pedidos_cancelados"] == []

    # Aislamiento vendedor 1: solo ve sus proformas y pedidos, no los de v2
    resp_v1 = _autenticar(v1).get("/api/v1/dashboard/tienda/?moneda=BOB")
    assert resp_v1.status_code == 200
    d_v1 = resp_v1.json()
    assert d_v1["indicadores"]["proformas_formalizadas"] == 1
    assert d_v1["indicadores"]["borradores"] == 0
    assert d_v1["indicadores"]["pedidos_generados"] == 1


@pytest.mark.django_db
def test_filtros_temporales_comparacion_periodos_y_zona_horaria():
    admin, v1, _, _ = _crear_usuarios()
    cli = cliente_persona(v1)

    # Período anterior: 2026-10-01 al 2026-10-10 (1 formalizada, 0 pedidos)
    _crear_proforma_mueble(vendedor=v1, cliente=cli, fecha=date(2026, 10, 5))
    # Período actual: 2026-10-11 al 2026-10-20 (2 formalizadas, 1 pedido)
    p_act1 = _crear_proforma_mueble(vendedor=v1, cliente=cli, fecha=date(2026, 10, 12))
    _crear_proforma_mueble(vendedor=v1, cliente=cli, fecha=date(2026, 10, 18))
    with reloj_comercial_simulado(
        date(2026, 10, 20),
        fecha_hora=datetime(2026, 10, 20, 22, 30, tzinfo=TZ_LA_PAZ),  # 2026-10-21 02:30 UTC
    ):
        aprobar_proforma(proforma_id=p_act1.id, actor=v1)

    resp = _autenticar(admin).get(
        "/api/v1/dashboard/administrador/comercial/"
        "?fecha_desde=2026-10-11&fecha_hasta=2026-10-20&granularidad=diaria"
    )
    assert resp.status_code == 200
    data = resp.json()
    ind = data["indicadores"]
    assert ind["proformas_formalizadas"] == 2
    assert ind["pedidos_generados"] == 1
    assert float(ind["tasa_conversion_cohorte"]) == 50.0
    comp = ind["comparaciones_periodo_anterior"]
    assert comp["periodo_anterior"] == {"fecha_desde": "2026-10-01", "fecha_hasta": "2026-10-10"}
    assert comp["proformas_formalizadas"]["actual"] == 2
    assert comp["proformas_formalizadas"]["anterior"] == 1
    assert comp["proformas_formalizadas"]["diferencia"] == 1
    assert float(comp["proformas_formalizadas"]["variacion_porcentaje"]) == 100.0

    # Pedido confirmado a las 22:30 America/La_Paz del 2026-10-20 cae en 2026-10-20
    puntos = {p["periodo"]: p for p in data["evolucion"]["puntos_conteo"]}
    assert puntos["2026-10-20"]["pedidos_generados"] == 1
    assert "2026-10-21" not in puntos

    # Validación de rango inválido
    bad = _autenticar(admin).get(
        "/api/v1/dashboard/administrador/?fecha_desde=2026-10-20&fecha_hasta=2026-10-10"
    )
    assert bad.status_code == 400


@pytest.mark.django_db
def test_taller_excluye_tecnicas_calcula_duracion_real_y_no_duplica_cola_ni_filtra_montos():
    admin, v1, _, jefe = _crear_usuarios()
    cli = cliente_persona(v1)
    prod = silla(admin, sku="S-TALLER-1", precio="300.00", stock=0)
    cargar_stock(prod, admin, Decimal("10.0000"))

    f_ini = date(2026, 11, 1)
    # Orden 1: funcional (MUEBLE_MEDIDA), terminada con historial EN_PROCESO -> TERMINADA (48h)
    p_func1 = _crear_proforma_mueble(
        vendedor=v1, cliente=cli, fecha=f_ini, precio="2500.00", tipo_mueble_codigo="ESCRITORIO"
    )
    with reloj_comercial_simulado(f_ini, fecha_hora=datetime(2026, 11, 1, 9, 0, tzinfo=TZ_LA_PAZ)):
        ped_f1 = aprobar_proforma(proforma_id=p_func1.id, actor=v1)
        ot_f1 = OrdenTrabajo.objects.get(pedido=ped_f1)
        ot_f1.fecha_entrega = date(2026, 11, 10)
        ot_f1.save(update_fields=["fecha_entrega"])

    with reloj_comercial_simulado(
        date(2026, 11, 2), fecha_hora=datetime(2026, 11, 2, 10, 0, tzinfo=TZ_LA_PAZ)
    ):
        cambiar_estado_orden_trabajo(
            orden_trabajo_id=ot_f1.id, actor=jefe, estado_codigo="EN_PROCESO"
        )
    with reloj_comercial_simulado(
        date(2026, 11, 4), fecha_hora=datetime(2026, 11, 4, 10, 0, tzinfo=TZ_LA_PAZ)
    ):
        cambiar_estado_orden_trabajo(
            orden_trabajo_id=ot_f1.id, actor=jefe, estado_codigo="TERMINADA"
        )
        cambiar_estado_pedido(pedido_id=ped_f1.id, actor=v1, estado_codigo="LISTO_ENTREGA")

    # Orden 2: funcional pendiente y vencida (coinciden varias condiciones en cola)
    p_func2 = _crear_proforma_mueble(
        vendedor=v1, cliente=cli, fecha=f_ini, precio="1800.00", tipo_mueble_codigo="CREDENZA"
    )
    with reloj_comercial_simulado(f_ini, fecha_hora=datetime(2026, 11, 1, 12, 0, tzinfo=TZ_LA_PAZ)):
        ped_f2 = aprobar_proforma(proforma_id=p_func2.id, actor=v1)
        ot_f2 = OrdenTrabajo.objects.get(pedido=ped_f2)
        ot_f2.fecha_entrega = date(2026, 11, 5)
        ot_f2.save(update_fields=["fecha_entrega"])

    # Orden 3: técnica (solo silla), excluida de taller e incluida en admin.ordenes_tecnicas_total
    p_tec = _crear_proforma_producto(vendedor=v1, cliente=cli, producto=prod, fecha=f_ini)
    with reloj_comercial_simulado(f_ini):
        aprobar_proforma(proforma_id=p_tec.id, actor=v1)

    with reloj_comercial_simulado(date(2026, 11, 8)):
        resp_tal = _autenticar(jefe).get(
            "/api/v1/dashboard/taller/?entrega_desde=2026-11-01&entrega_hasta=2026-11-20"
        )
        assert resp_tal.status_code == 200
        d_tal = resp_tal.json()
        ind = d_tal["indicadores"]
        assert ind["pendientes"] == 1
        assert ind["terminadas"] == 1
        assert ind["tiempo_promedio_fabricacion_horas"] == 48.0
        assert ind["tiempo_promedio_fabricacion_dias"] == 2.0
        # Cola sin duplicación: ot_f2 aparece 1 sola vez como ENTREGA_VENCIDA
        cola = d_tal["cola_prioridades"]["results"]
        ot_ids = [item["orden_trabajo_id"] for item in cola]
        assert len(ot_ids) == len(set(ot_ids)) == 2
        assert cola[0]["orden_trabajo_id"] == ot_f2.id
        assert cola[0]["categoria_prioridad"] == "ENTREGA_VENCIDA"
        # Ningún monto financiero expuesto en taller
        texto_resp = str(d_tal)
        assert "2500" not in texto_resp
        assert "1800" not in texto_resp
        assert "saldo" not in texto_resp.lower()

        # Planificación distingue planificada vs efectiva
        resp_plan = _autenticar(jefe).get(
            "/api/v1/dashboard/taller/planificacion/"
            "?entrega_desde=2026-11-01&entrega_hasta=2026-11-20"
        )
        assert resp_plan.status_code == 200
        eventos = resp_plan.json()["calendario_eventos"]["results"]
        assert any(e["naturaleza"] == "PLANIFICADA" for e in eventos)
        assert any(e["naturaleza"] == "EFECTIVA" for e in eventos)

        # Admin contabiliza técnicas por separado
        resp_adm = _autenticar(admin).get(f"/api/v1/dashboard/administrador/?vendedor={v1.id}")
        assert resp_adm.status_code == 200
        prod_adm = resp_adm.json()["produccion"]
        assert prod_adm["ordenes_fabricacion_total"] == 2
        assert prod_adm["ordenes_tecnicas_total"] == 1


@pytest.mark.django_db
def test_registros_historicos_incompletos_y_rendimiento_queries():
    admin, v1, _, jefe = _crear_usuarios()
    cli = cliente_persona(v1)
    # Producto sin stock_minimo (histórico)
    p_hist = silla(admin, sku="S-HIST", precio="100.00", stock=0)
    cargar_stock(p_hist, admin, Decimal("5.0000"))
    # Proforma sin validez_oferta y OT terminada sin transición EN_PROCESO en historial
    p = _crear_proforma_mueble(vendedor=v1, cliente=cli, fecha=date(2026, 11, 1), validez=None)
    with reloj_comercial_simulado(date(2026, 11, 1)):
        ped = aprobar_proforma(proforma_id=p.id, actor=v1)
        ot = OrdenTrabajo.objects.get(pedido=ped)
        ot.estado = valor("ESTADO_ORDEN_TRABAJO", "TERMINADA")
        ot.save(update_fields=["estado"])
        HistorialEstadoOrdenTrabajo.objects.create(
            orden_trabajo=ot,
            estado_anterior=valor("ESTADO_ORDEN_TRABAJO", "PENDIENTE"),
            estado_nuevo=valor("ESTADO_ORDEN_TRABAJO", "TERMINADA"),
            cambiado_por=jefe,
            fecha=datetime(2026, 11, 3, 12, 0, tzinfo=TZ_LA_PAZ),
        )

    c_admin = _autenticar(admin)
    with CaptureQueriesContext(connection) as ctx_adm:
        resp_adm = c_admin.get("/api/v1/dashboard/administrador/")
    assert resp_adm.status_code == 200
    assert len(ctx_adm) <= 35

    c_tal = _autenticar(jefe)
    with CaptureQueriesContext(connection) as ctx_tal:
        resp_tal = c_tal.get("/api/v1/dashboard/taller/")
    assert resp_tal.status_code == 200
    # Al no tener EN_PROCESO, la duración no se inventa y devuelve None
    assert resp_tal.json()["indicadores"]["tiempo_promedio_fabricacion_horas"] is None
    assert len(ctx_tal) <= 25
