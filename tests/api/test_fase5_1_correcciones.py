"""Pruebas de regresión para Fase 5.1: PDFs, Excel, filtros y latencia ASR."""

import io
import shutil
import subprocess
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.auth.models import Group
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.capturas.asistidas import resultado_asistida
from apps.capturas.catalogo import resultado_catalogo
from apps.capturas.models import Captura, IntentoCaptura
from apps.catalogo.models import Producto, ValorCatalogo
from apps.clientes.models import Cliente
from apps.documentos.pdf import (
    _spanish_date,
    renderizar_orden_trabajo_pdf,
    renderizar_proforma_pdf,
)
from apps.documentos.pdf_recibo import renderizar_recibo_pdf
from apps.movimientos_stock.services import registrar_ajuste_stock
from apps.pedidos.models import Pedido
from apps.pedidos.services import aprobar_proforma
from apps.proformas.models import DetalleProforma
from apps.proformas.services import crear_proforma
from apps.recibos.services import emitir_recibo_idempotente


def _user(username: str, group_name: str) -> User:
    user = User.objects.create_user(username=username, password="x", is_active=True)
    group, _ = Group.objects.get_or_create(name=group_name)
    user.groups.add(group)
    return user


def _setup_flujo_completo():
    vendedor = _user(f"vend_{uuid4().hex[:6]}", "ENCARGADO_TIENDA")
    admin = User.objects.create_user(
        username=f"adm_{uuid4().hex[:6]}", password="x", is_active=True, is_staff=True
    )
    jefe = _user(f"jefe_{uuid4().hex[:6]}", "JEFE_TALLER")
    tipo_cli = ValorCatalogo.objects.get(concepto__codigo="TIPO_CLIENTE", codigo="PERSONA")
    cliente = Cliente.objects.create(
        tipo_cliente=tipo_cli,
        nombres="Carlos",
        apellidos="Mendoza",
        celular="71234567",
        direccion="Av. Principal 123",
    )
    pf = crear_proforma(
        actor=vendedor,
        moneda_codigo="BOB",
        cliente=cliente,
        titulo="Escritorio ejecutivo",
    )
    tipo_item = ValorCatalogo.objects.get(concepto__codigo="TIPO_ITEM", codigo="OTRO")
    unidad_stock = ValorCatalogo.objects.get(concepto__codigo="UNIDAD_MEDIDA", codigo="PIEZA")
    cat = ValorCatalogo.objects.get(concepto__codigo="CATEGORIA_PRODUCTO", codigo="OTRO")
    prod = Producto.objects.create(
        sku=f"SKU-{uuid4().hex[:6]}",
        nombre="Estante Modular Pro",
        categoria=cat,
        unidad_stock=unidad_stock,
        precio_lista=Decimal("500.00"),
        stock=Decimal("0.0000"),
    )
    registrar_ajuste_stock(
        actor=admin,
        producto_id=prod.id,
        tipo_operacion="ENTRADA",
        cantidad=Decimal("10.0000"),
        motivo="REPOSICION",
        observaciones="Stock inicial prueba",
        clave_idempotencia=str(uuid4()),
    )
    DetalleProforma.objects.create(
        proforma=pf,
        tipo_item=tipo_item,
        producto=prod,
        nombre=prod.nombre,
        cantidad=Decimal("2.0000"),
        unidad=unidad_stock,
        precio_unitario=Decimal("500.00"),
        descuento=Decimal("0.00"),
        total=Decimal("1000.00"),
    )
    pf.subtotal = Decimal("1000.00")
    pf.total = Decimal("1000.00")
    pf.estado = ValorCatalogo.objects.get(concepto__codigo="ESTADO_PROFORMA", codigo="ENVIADA")
    pf.save(update_fields=["estado", "subtotal", "total"])
    aprobar_proforma(proforma_id=pf.id, actor=vendedor)
    pedido = Pedido.objects.get(proforma=pf)
    ot = pedido.ordentrabajo
    tipo_pago = ValorCatalogo.objects.get(concepto__codigo="TIPO_PAGO", codigo="EFECTIVO")
    recibo, _ = emitir_recibo_idempotente(
        pedido=pedido,
        actor=vendedor,
        clave_idempotencia=str(uuid4()),
        nombre_completo="Carlos Mendoza",
        monto_en_letras="Mil 00/100 Bolivianos",
        concepto="Pago completo",
        tipo_pago=tipo_pago,
        pago_actual=Decimal("1000.00"),
    )
    return vendedor, jefe, cliente, prod, pf, pedido, ot, recibo


@pytest.mark.django_db
def test_pdfs_muestran_solo_fecha_generacion_sin_prefijos():
    vendedor, jefe, _cli, _prod, pf, _ped, ot, recibo = _setup_flujo_completo()
    fecha_hoy = _spanish_date(timezone.localdate())

    raw_pf = renderizar_proforma_pdf(pf.id, usuario=vendedor)
    raw_ot = renderizar_orden_trabajo_pdf(ot.id, usuario=jefe)
    raw_rec = renderizar_recibo_pdf(recibo.id, usuario=vendedor)

    if shutil.which("pdftotext"):
        for raw in (raw_pf, raw_ot):
            txt = subprocess.check_output(["pdftotext", "-", "-"], input=raw).decode(
                "utf-8", errors="replace"
            )
            assert fecha_hoy in txt
            assert "Emisión:" not in txt
            assert "Generado:" not in txt
        txt_rec = subprocess.check_output(["pdftotext", "-", "-"], input=raw_rec).decode(
            "utf-8", errors="replace"
        )
        assert fecha_hoy in txt_rec
        assert "Fecha:" not in txt_rec
    else:
        for raw in (raw_pf, raw_ot, raw_rec):
            assert raw.startswith(b"%PDF")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/v1/proformas/exportar-excel/",
        "/api/v1/pedidos/exportar-excel/",
        "/api/v1/ordenes-trabajo/exportar-excel/",
        "/api/v1/notas-entrega/exportar-excel/",
        "/api/v1/recibos/exportar-excel/",
        "/api/v1/movimientos-stock/exportar-excel/",
    ],
)
def test_exportaciones_excel_rechazan_rangos_invalidos_con_400(endpoint):
    vendedor = _user(f"exp_{uuid4().hex[:6]}", "ENCARGADO_TIENDA")
    client = APIClient()
    client.force_authenticate(user=vendedor)

    hoy = timezone.localdate()
    ayer = hoy - timedelta(days=1)
    manana = hoy + timedelta(days=1)

    r_invertido = client.get(
        endpoint,
        {"fecha_desde": hoy.isoformat(), "fecha_hasta": ayer.isoformat()},
    )
    assert r_invertido.status_code == 400

    r_futura = client.get(
        endpoint,
        {"fecha_desde": hoy.isoformat(), "fecha_hasta": manana.isoformat()},
    )
    assert r_futura.status_code == 400

    r_invalida = client.get(endpoint, {"fecha_desde": "2026-99-99"})
    assert r_invalida.status_code == 400


@pytest.mark.django_db
def test_movimientos_excel_exporta_sin_fechas_y_con_nombre_legible():
    vendedor, _jefe, _cli, prod, _pf, _ped, _ot, _rec = _setup_flujo_completo()
    client = APIClient()
    client.force_authenticate(user=vendedor)

    resp = client.get("/api/v1/movimientos-stock/exportar-excel/", {"producto": prod.id})
    assert resp.status_code == 200
    disposition = resp["Content-Disposition"]
    assert "reporte-stock" in disposition
    assert prod.sku.lower() in disposition
    wb = load_workbook(io.BytesIO(resp.content))
    ws = wb.active
    assert ws.max_row >= 4


@pytest.mark.django_db
def test_pedidos_excel_acepta_estado_id_y_codigo_y_nombre_legible():
    vendedor, _jefe, cliente, _prod, pf, pedido, _ot, _rec = _setup_flujo_completo()
    client = APIClient()
    client.force_authenticate(user=vendedor)

    r_id = client.get("/api/v1/pedidos/exportar-excel/", {"estado": str(pedido.estado_id)})
    r_cod = client.get("/api/v1/pedidos/exportar-excel/", {"estado": pedido.estado.codigo})
    assert r_id.status_code == 200
    assert r_cod.status_code == 200
    assert r_id["Content-Disposition"] == r_cod["Content-Disposition"]

    r_pf = client.get("/api/v1/proformas/exportar-excel/", {"cliente": str(cliente.id)})
    assert r_pf.status_code == 200
    assert "carlos-mendoza" in r_pf["Content-Disposition"]


@pytest.mark.django_db
def test_capturas_exponen_latencia_asr_ms():
    vendedor = _user(f"cap_{uuid4().hex[:6]}", "ENCARGADO_TIENDA")
    cap = Captura.objects.create(
        vendedor=vendedor,
        clave_idempotencia=uuid4(),
        capturado_at=timezone.now(),
        modo_captura="ASISTIDA_CREACION_MUEBLE",
        sesion_borrador=str(uuid4()),
        moneda_contexto_codigo="BOB",
        estado="COMPLETADA",
        texto_transcrito="Una mesa de melamina de 120 por 60 cm",
    )
    IntentoCaptura.objects.create(
        captura=cap,
        numero_intento=1,
        estado="FINALIZADO",
        modelo_asr_version="faster-whisper-small",
        inicio_at=timezone.now(),
        latencia_asr_ms=2345,
        resultado_raw={"solo_transcribir": True},
    )
    res_asist = resultado_asistida(cap)
    assert res_asist["latencia_asr_ms"] == 2345

    cap_cat = Captura.objects.create(
        vendedor=vendedor,
        clave_idempotencia=uuid4(),
        capturado_at=timezone.now(),
        modo_captura="CATALOGO_CREACION",
        categoria_catalogo="SILLA",
        sesion_borrador=str(uuid4()),
        estado="COMPLETADA",
        texto_transcrito="Silla ergonómica negra",
    )
    IntentoCaptura.objects.create(
        captura=cap_cat,
        numero_intento=1,
        estado="FINALIZADO",
        modelo_asr_version="faster-whisper-small",
        inicio_at=timezone.now(),
        latencia_asr_ms=1780,
        resultado_raw={"solo_transcribir": True},
    )
    res_cat = resultado_catalogo(cap_cat)
    assert res_cat["latencia_asr_ms"] == 1780
