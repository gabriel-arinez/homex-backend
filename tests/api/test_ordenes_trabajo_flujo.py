from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from apps.catalogo.models import ValorCatalogo
from apps.ordenes_trabajo.models import HistorialEstadoOrdenTrabajo, OrdenTrabajo
from apps.pedidos.services import aprobar_proforma, cambiar_estado_pedido
from apps.proformas.services import (
    agregar_detalle,
    crear_especificacion,
    crear_proforma,
    enviar_proforma,
)
from tests.factories import cargar_stock, cliente_persona, silla


@pytest.mark.django_db
def test_flujo_ot_permisos_timeline_y_bloqueo_listo_entrega(django_user_model):
    encargado = django_user_model.objects.create_user(
        username="encargado-ot-test",
        password="HomexTestPassword123!",
    )
    encargado.groups.add(Group.objects.get(name="ENCARGADO_TIENDA"))

    jefe = django_user_model.objects.create_user(
        username="jefe-taller-ot-test",
        password="HomexTestPassword123!",
    )
    jefe.groups.add(Group.objects.get(name="JEFE_TALLER"))

    cli = cliente_persona(encargado)
    unidad_pieza = ValorCatalogo.objects.get(
        concepto__codigo="UNIDAD_MEDIDA",
        codigo="PIEZA",
    )
    tipo_mueble = ValorCatalogo.objects.get(
        concepto__codigo="TIPO_ITEM",
        codigo="MUEBLE_MEDIDA",
    )

    # Pedido 1: con mueble a medida (requiere OT funcional terminada)
    pf_mueble = crear_proforma(
        actor=encargado,
        moneda_codigo="BOB",
        titulo="Escritorio a medida",
        cliente=cli,
    )
    det_mueble = agregar_detalle(
        proforma_id=pf_mueble.id,
        actor=encargado,
        tipo_item=tipo_mueble,
        nombre="Escritorio ejecutivo",
        cantidad=Decimal("1"),
        unidad=unidad_pieza,
        precio_unitario=Decimal("1500.00"),
    )
    crear_especificacion(
        detalle_id=det_mueble.id,
        actor=encargado,
        tipo_mueble=ValorCatalogo.objects.get(concepto__codigo="TIPO_MUEBLE", codigo="ESCRITORIO"),
        datos_tecnicos={"dimensiones": {"largo_mm": 1600, "ancho_mm": 700, "alto_mm": 750}},
    )
    enviar_proforma(proforma_id=pf_mueble.id, actor=encargado)
    ped_mueble = aprobar_proforma(proforma_id=pf_mueble.id, actor=encargado)
    ot_mueble = OrdenTrabajo.objects.get(pedido=ped_mueble)

    # Historial inicial registrado al aprobar
    assert HistorialEstadoOrdenTrabajo.objects.filter(
        orden_trabajo=ot_mueble, estado_nuevo__codigo="PENDIENTE"
    ).exists()

    # Pasar pedido a EN_PRODUCCION -> OT pasa a EN_PROCESO y registra historial
    cambiar_estado_pedido(
        pedido_id=ped_mueble.id,
        actor=encargado,
        estado_codigo="EN_PRODUCCION",
    )
    ot_mueble.refresh_from_db()
    assert ot_mueble.estado.codigo == "EN_PROCESO"

    # ENCARGADO_TIENDA no puede cambiar el estado de la OT
    api_encargado = APIClient()
    api_encargado.force_authenticate(user=encargado)
    resp_forb_estado = api_encargado.post(
        f"/api/v1/ordenes-trabajo/{ot_mueble.id}/cambiar-estado/",
        {"estado_codigo": "TERMINADA"},
        format="json",
    )
    assert resp_forb_estado.status_code == 403

    resp_forb_ready = api_encargado.post(
        f"/api/v1/ordenes-trabajo/{ot_mueble.id}/marcar-listo-entrega/",
        format="json",
    )
    assert resp_forb_ready.status_code == 403

    # Pedido -> LISTO_ENTREGA se bloquea mientras la OT no esté TERMINADA
    resp_bloqueado = api_encargado.post(
        f"/api/v1/pedidos/{ped_mueble.id}/cambiar-estado/",
        {"estado_codigo": "LISTO_ENTREGA"},
        format="json",
    )
    assert resp_bloqueado.status_code == 400

    # JEFE_TALLER sí puede terminar la OT y expone timeline completo
    api_jefe = APIClient()
    api_jefe.force_authenticate(user=jefe)
    resp_term = api_jefe.post(
        f"/api/v1/ordenes-trabajo/{ot_mueble.id}/cambiar-estado/",
        {"estado_codigo": "TERMINADA", "observaciones": "Control de calidad OK"},
        format="json",
    )
    assert resp_term.status_code == 200
    assert resp_term.data["estado_info"]["codigo"] == "TERMINADA"
    codigos_timeline = [
        item["estado_nuevo_info"]["codigo"] for item in resp_term.data["historial_estados"]
    ]
    assert codigos_timeline == ["PENDIENTE", "EN_PROCESO", "TERMINADA"]

    # Ahora ENCARGADO_TIENDA sí puede pasar el pedido a LISTO_ENTREGA
    resp_ok = api_encargado.post(
        f"/api/v1/pedidos/{ped_mueble.id}/cambiar-estado/",
        {"estado_codigo": "LISTO_ENTREGA"},
        format="json",
    )
    assert resp_ok.status_code == 200
    ped_mueble.refresh_from_db()
    assert ped_mueble.estado.codigo == "LISTO_ENTREGA"

    # Pedido 2: solo catálogo (no requiere OT funcional) pasa directo a LISTO_ENTREGA
    prod = silla(encargado, sku="SILLA-OT-TEST", precio="400.00")
    cargar_stock(prod, encargado, Decimal("5"))
    tipo_silla = ValorCatalogo.objects.get(concepto__codigo="TIPO_ITEM", codigo="SILLA")
    pf_cat = crear_proforma(
        actor=encargado,
        moneda_codigo="BOB",
        titulo="Solo silla",
        cliente=cli,
    )
    agregar_detalle(
        proforma_id=pf_cat.id,
        actor=encargado,
        tipo_item=tipo_silla,
        producto=prod,
        nombre=prod.nombre,
        cantidad=Decimal("1"),
        unidad=unidad_pieza,
        precio_unitario=Decimal("400.00"),
    )
    enviar_proforma(proforma_id=pf_cat.id, actor=encargado)
    ped_cat = aprobar_proforma(proforma_id=pf_cat.id, actor=encargado)
    resp_cat_ok = api_encargado.post(
        f"/api/v1/pedidos/{ped_cat.id}/cambiar-estado/",
        {"estado_codigo": "LISTO_ENTREGA"},
        format="json",
    )
    assert resp_cat_ok.status_code == 200
    ped_cat.refresh_from_db()
    assert ped_cat.estado.codigo == "LISTO_ENTREGA"
