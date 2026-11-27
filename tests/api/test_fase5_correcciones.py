from datetime import timedelta
from io import BytesIO

import pytest
from django.contrib.auth.models import Group
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.test import APIClient

from apps.catalogo.models import Producto, ValorCatalogo
from apps.clientes.models import Cliente
from apps.core.permissions import NOMBRE_GRUPO_JEFE_TALLER
from apps.ordenes_trabajo.services import cambiar_estado_orden_trabajo
from apps.pedidos.models import HistorialEstadoPedido
from apps.pedidos.services import aprobar_proforma, cancelar_pedido
from apps.proformas.models import HistorialEstadoProforma
from apps.proformas.services import (
    agregar_detalle,
    crear_especificacion,
    crear_proforma,
    enviar_proforma,
    registrar_historial_estado_proforma,
    vencer_proformas,
)
from tests.factories import vendedor


def jefe_taller(user):
    grupo, _ = Group.objects.get_or_create(name=NOMBRE_GRUPO_JEFE_TALLER)
    user.groups.add(grupo)
    return user


@pytest.mark.django_db
def test_fase5_historial_estados_proforma_pedido_manual_automatico_e_idempotente(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="f5-vend"))
    taller = jefe_taller(django_user_model.objects.create_user(username="f5-taller"))
    tipo_cli = ValorCatalogo.objects.get(concepto__codigo="TIPO_CLIENTE", codigo="PERSONA")
    cliente = Cliente.objects.create(
        tipo_cliente=tipo_cli,
        nombres="Ana",
        apellidos="Gómez",
        celular="71234567",
        direccion="Av. Ballivián 100",
    )
    tipo_item = ValorCatalogo.objects.get(concepto__codigo="TIPO_ITEM", codigo="MUEBLE_MEDIDA")
    unidad = ValorCatalogo.objects.get(concepto__codigo="UNIDAD_MEDIDA", codigo="PIEZA")

    pf = crear_proforma(actor=actor, cliente=cliente, titulo="Escritorio =SUM(1,2)")
    det = agregar_detalle(
        proforma_id=pf.id,
        actor=actor,
        tipo_item=tipo_item,
        nombre="Escritorio ejecutivo",
        cantidad=1,
        unidad=unidad,
        precio_unitario=1200,
    )
    crear_especificacion(
        detalle_id=det.id,
        actor=actor,
        datos_tecnicos={"componentes": [{"nombre": "Tapa", "material": "Melamina"}]},
    )
    pf = enviar_proforma(proforma_id=pf.id, actor=actor)
    # Idempotency: re-recording same state does not duplicate
    registrar_historial_estado_proforma(
        proforma=pf,
        estado_anterior=pf.estado,
        estado_nuevo=pf.estado,
        actor=actor,
    )
    assert HistorialEstadoProforma.objects.filter(proforma=pf).count() == 2

    pedido = aprobar_proforma(proforma_id=pf.id, actor=actor)
    assert HistorialEstadoProforma.objects.filter(proforma=pf).count() == 3
    assert HistorialEstadoPedido.objects.filter(pedido=pedido).count() == 1

    ot = pedido.ordentrabajo
    cambiar_estado_orden_trabajo(orden_trabajo_id=ot.id, actor=taller, estado_codigo="EN_PROCESO")
    hist_ped = list(HistorialEstadoPedido.objects.filter(pedido=pedido).order_by("id"))
    assert len(hist_ped) == 2
    assert hist_ped[1].estado_nuevo.codigo == "EN_PRODUCCION"
    assert hist_ped[1].es_automatico is True
    assert hist_ped[1].origen == "SISTEMA"

    cancelar_pedido(pedido_id=pedido.id, actor=actor)
    assert HistorialEstadoPedido.objects.filter(pedido=pedido).count() == 3

    # Celery expiration creates automatic CELERY history entry
    pf_exp = crear_proforma(
        actor=actor, cliente=cliente, titulo="Proforma vencida", validez_oferta=1
    )
    det_exp = agregar_detalle(
        proforma_id=pf_exp.id,
        actor=actor,
        tipo_item=tipo_item,
        nombre="Estante",
        cantidad=1,
        unidad=unidad,
        precio_unitario=500,
    )
    crear_especificacion(
        detalle_id=det_exp.id,
        actor=actor,
        datos_tecnicos={"componentes": [{"nombre": "Cuerpo", "material": "Melamina"}]},
    )
    pf_exp = enviar_proforma(proforma_id=pf_exp.id, actor=actor)
    pf_exp.fecha = timezone.localdate() - timedelta(days=5)
    pf_exp.save(update_fields=["fecha"])
    assert vencer_proformas() >= 1
    ultimo = HistorialEstadoProforma.objects.filter(proforma=pf_exp).order_by("-id").first()
    assert ultimo.estado_nuevo.codigo == "VENCIDA"
    assert ultimo.es_automatico is True
    assert ultimo.origen == "CELERY"


@pytest.mark.django_db
def test_fase5_exportar_excel_bandejas_y_seguridad_formulas(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="f5-excel-v"))
    taller = jefe_taller(django_user_model.objects.create_user(username="f5-excel-t"))
    tipo_cli = ValorCatalogo.objects.get(concepto__codigo="TIPO_CLIENTE", codigo="PERSONA")
    Cliente.objects.create(
        tipo_cliente=tipo_cli,
        nombres='=HYPERLINK("http://evil","Bob")',
        apellidos="Pérez",
        celular="70001122",
        direccion="Calle 1",
    )
    cat = ValorCatalogo.objects.get(concepto__codigo="CATEGORIA_PRODUCTO", codigo="OTRO")
    unidad = ValorCatalogo.objects.get(concepto__codigo="UNIDAD_MEDIDA", codigo="PIEZA")
    Producto.objects.create(
        sku="F5-XLSX-1",
        nombre="+Producto prueba",
        categoria=cat,
        unidad_stock=unidad,
        precio_lista=100,
        stock=0,
    )

    client = APIClient()
    client.force_authenticate(user=actor)

    from django.utils import timezone

    hoy = str(timezone.localdate())
    endpoints = [
        "/api/v1/proformas/exportar-excel/",
        "/api/v1/catalogo/productos/exportar-excel/",
        "/api/v1/pedidos/exportar-excel/",
        "/api/v1/ordenes-trabajo/exportar-excel/",
        "/api/v1/notas-entrega/exportar-excel/",
        "/api/v1/clientes/exportar-excel/",
        "/api/v1/recibos/exportar-excel/",
    ]
    for url in endpoints:
        # Sin rango de fechas debe rechazar con HTTP 400
        assert client.get(url).status_code == 400, url
        assert client.get(url, {"fecha_desde": hoy}).status_code == 400, url
        assert client.get(url, {"fecha_hasta": hoy}).status_code == 400, url

        resp = client.get(url, {"fecha_desde": hoy, "fecha_hasta": hoy})
        assert resp.status_code == 200, url
        assert (
            resp["Content-Type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        wb = load_workbook(BytesIO(resp.content))
        assert wb.active is not None

    # Check formula injection neutralized in Clientes Excel (requiere rango válido)
    cli_resp = client.get(
        "/api/v1/clientes/exportar-excel/", {"fecha_desde": hoy, "fecha_hasta": hoy}
    )
    assert cli_resp.status_code == 200
    wb_cli = load_workbook(BytesIO(cli_resp.content))
    ws_cli = wb_cli.active
    assert ws_cli is not None

    # Check JEFE_TALLER cannot export financial trays, and OT Excel has no financial headers
    taller_client = APIClient()
    taller_client.force_authenticate(user=taller)
    assert (
        taller_client.get(
            "/api/v1/proformas/exportar-excel/", {"fecha_desde": hoy, "fecha_hasta": hoy}
        ).status_code
        == 403
    )
    ot_resp = taller_client.get(
        "/api/v1/ordenes-trabajo/exportar-excel/", {"fecha_desde": hoy, "fecha_hasta": hoy}
    )
    assert ot_resp.status_code == 200
    wb_ot = load_workbook(BytesIO(ot_resp.content))
    headers_ot = [cell.value for cell in wb_ot.active[4]]
    assert "Total" not in headers_ot
    assert "Subtotal" not in headers_ot
