from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.db import DatabaseError, connection, transaction
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.catalogo.models import ValorCatalogo
from apps.clientes.models import Cliente
from apps.notas_entrega.models import NotaEntrega
from apps.ordenes_trabajo.models import HistorialEstadoOrdenTrabajo, OrdenTrabajo
from apps.ordenes_trabajo.services import cambiar_estado_orden_trabajo
from apps.pedidos.services import aprobar_proforma, cambiar_estado_pedido, cancelar_pedido
from apps.proformas.services import (
    agregar_detalle,
    crear_especificacion,
    crear_proforma,
    enviar_proforma,
)
from tests.factories import cargar_stock, cliente_persona, silla


def _crear_usuarios(django_user_model):
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

    staff = django_user_model.objects.create_user(
        username="staff-ot-test",
        password="HomexTestPassword123!",
        is_staff=True,
    )
    return encargado, jefe, staff


def _crear_pedido_mueble(encargado, cli, titulo="Escritorio a medida"):
    unidad_pieza = ValorCatalogo.objects.get(
        concepto__codigo="UNIDAD_MEDIDA",
        codigo="PIEZA",
    )
    tipo_mueble = ValorCatalogo.objects.get(
        concepto__codigo="TIPO_MUEBLE",
        codigo="ESCRITORIO",
    )
    tipo_item = ValorCatalogo.objects.get(
        concepto__codigo="TIPO_ITEM",
        codigo="MUEBLE_MEDIDA",
    )
    pf = crear_proforma(
        actor=encargado,
        moneda_codigo="BOB",
        titulo=titulo,
        cliente=cli,
    )
    det = agregar_detalle(
        proforma_id=pf.id,
        actor=encargado,
        tipo_item=tipo_item,
        nombre="Escritorio ejecutivo",
        cantidad=Decimal("1"),
        unidad=unidad_pieza,
        precio_unitario=Decimal("1500.00"),
    )
    crear_especificacion(
        detalle_id=det.id,
        actor=encargado,
        tipo_mueble=tipo_mueble,
        datos_tecnicos={"dimensiones": {"largo_mm": 1600, "ancho_mm": 700, "alto_mm": 750}},
    )
    enviar_proforma(proforma_id=pf.id, actor=encargado)
    ped = aprobar_proforma(proforma_id=pf.id, actor=encargado)
    ot = OrdenTrabajo.objects.get(pedido=ped)
    return ped, ot


@pytest.mark.django_db
def test_flujo_ot_invertido_permisos_timeline_y_listo_entrega(django_user_model):
    encargado, jefe, staff = _crear_usuarios(django_user_model)
    cli = cliente_persona(encargado)
    ped_mueble, ot_mueble = _crear_pedido_mueble(encargado, cli)

    # Historial inicial y logística prellenada desde el cliente
    assert HistorialEstadoOrdenTrabajo.objects.filter(
        orden_trabajo=ot_mueble, estado_nuevo__codigo="PENDIENTE"
    ).exists()
    assert ot_mueble.lugar_entrega == cli.direccion
    assert cli.nombres in (ot_mueble.responsable_recepcion or "")

    api_encargado = APIClient()
    api_encargado.force_authenticate(user=encargado)
    api_jefe = APIClient()
    api_jefe.force_authenticate(user=jefe)
    api_staff = APIClient()
    api_staff.force_authenticate(user=staff)

    # ENCARGADO_TIENDA no puede pasar pedido con mueble directo a EN_PRODUCCION
    resp_ped_prod = api_encargado.post(
        f"/api/v1/pedidos/{ped_mueble.id}/cambiar-estado/",
        {"estado_codigo": "EN_PRODUCCION"},
        format="json",
    )
    assert resp_ped_prod.status_code == 400

    # ENCARGADO_TIENDA tampoco puede cambiar el estado de la OT ni marcar_listo_entrega
    assert (
        api_encargado.post(
            f"/api/v1/ordenes-trabajo/{ot_mueble.id}/cambiar-estado/",
            {"estado_codigo": "EN_PROCESO"},
            format="json",
        ).status_code
        == 403
    )
    assert (
        api_encargado.post(
            f"/api/v1/ordenes-trabajo/{ot_mueble.id}/marcar-listo-entrega/",
            format="json",
        ).status_code
        == 403
    )

    # JEFE_TALLER no puede marcar listo entrega mientras la OT esté PENDIENTE
    assert (
        api_jefe.post(
            f"/api/v1/ordenes-trabajo/{ot_mueble.id}/marcar-listo-entrega/",
            format="json",
        ).status_code
        == 400
    )

    # JEFE_TALLER inicia fabricación: OT -> EN_PROCESO y Pedido se sincroniza a EN_PRODUCCION
    resp_iniciar = api_jefe.post(
        f"/api/v1/ordenes-trabajo/{ot_mueble.id}/cambiar-estado/",
        {"estado_codigo": "EN_PROCESO", "observaciones": "Corte e inicio en taller"},
        format="json",
    )
    assert resp_iniciar.status_code == 200
    assert resp_iniciar.data["estado_info"]["codigo"] == "EN_PROCESO"
    assert resp_iniciar.data["pedido_estado_codigo"] == "EN_PRODUCCION"
    ped_mueble.refresh_from_db()
    assert ped_mueble.estado.codigo == "EN_PRODUCCION"

    # JEFE_TALLER puede editar logística prellenada
    resp_patch_log = api_jefe.patch(
        f"/api/v1/ordenes-trabajo/{ot_mueble.id}/planificacion/",
        {"lugar_entrega": "Av. Costanera 500", "responsable_recepcion": "Recepción Obra"},
        format="json",
    )
    assert resp_patch_log.status_code == 200
    assert resp_patch_log.data["lugar_entrega"] == "Av. Costanera 500"

    # Bloqueado LISTO_ENTREGA mientras la OT sigue EN_PROCESO
    assert (
        api_encargado.post(
            f"/api/v1/pedidos/{ped_mueble.id}/cambiar-estado/",
            {"estado_codigo": "LISTO_ENTREGA"},
            format="json",
        ).status_code
        == 400
    )
    assert (
        api_jefe.post(
            f"/api/v1/ordenes-trabajo/{ot_mueble.id}/marcar-listo-entrega/",
            format="json",
        ).status_code
        == 400
    )

    # JEFE_TALLER termina la OT -> timeline completo PENDIENTE -> EN_PROCESO -> TERMINADA
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

    # Ahora JEFE_TALLER marca listo para entrega y se emite NotaEntrega
    resp_ready = api_jefe.post(
        f"/api/v1/ordenes-trabajo/{ot_mueble.id}/marcar-listo-entrega/",
        format="json",
    )
    assert resp_ready.status_code == 200
    ped_mueble.refresh_from_db()
    assert ped_mueble.estado.codigo == "LISTO_ENTREGA"
    assert NotaEntrega.objects.filter(pedido=ped_mueble).exists()

    # Perfil staff conserva acceso operativo
    assert api_staff.get(f"/api/v1/ordenes-trabajo/{ot_mueble.id}/").status_code == 200


@pytest.mark.django_db
def test_ot_bloquea_cancelacion_independiente_y_triggers_pg(django_user_model):
    encargado, jefe, _ = _crear_usuarios(django_user_model)
    cli = cliente_persona(encargado)
    ped, ot = _crear_pedido_mueble(encargado, cli, titulo="Mueble cancelación")

    api_jefe = APIClient()
    api_jefe.force_authenticate(user=jefe)

    # No se puede cancelar OT de forma independiente
    resp_cancel_ot = api_jefe.post(
        f"/api/v1/ordenes-trabajo/{ot.id}/cambiar-estado/",
        {"estado_codigo": "CANCELADA"},
        format="json",
    )
    assert resp_cancel_ot.status_code == 400

    with pytest.raises(ValidationError):
        cambiar_estado_orden_trabajo(
            orden_trabajo_id=ot.id,
            actor=jefe,
            estado_codigo="CANCELADA",
        )

    # Triggers PostgreSQL bloquean bypass directo por SQL
    estado_listo = ValorCatalogo.objects.get(
        concepto__codigo="ESTADO_PEDIDO", codigo="LISTO_ENTREGA"
    )
    estado_ot_canc = ValorCatalogo.objects.get(
        concepto__codigo="ESTADO_ORDEN_TRABAJO", codigo="CANCELADA"
    )
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    "UPDATE pedidos SET estado_id = %s WHERE id = %s",
                    [estado_listo.id, ped.id],
                )
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    "UPDATE ordenes_trabajo SET estado_id = %s WHERE id = %s",
                    [estado_ot_canc.id, ot.id],
                )

    # Cancelación comercial oficial cancela pedido y OT coherentemente
    cancelar_pedido(pedido_id=ped.id, actor=encargado)
    ped.refresh_from_db()
    ot.refresh_from_db()
    assert ped.estado.codigo == "CANCELADO"
    assert ot.estado.codigo == "CANCELADA"


@pytest.mark.django_db
def test_pedido_mixto_y_solo_catalogo(django_user_model):
    encargado, jefe, _ = _crear_usuarios(django_user_model)
    cli = cliente_persona(encargado)
    prod = silla(encargado, sku="SILLA-OT-MIX", precio="400.00")
    cargar_stock(prod, encargado, Decimal("5"))
    unidad_pieza = ValorCatalogo.objects.get(concepto__codigo="UNIDAD_MEDIDA", codigo="PIEZA")
    tipo_silla = ValorCatalogo.objects.get(concepto__codigo="TIPO_ITEM", codigo="SILLA")
    tipo_mueble = ValorCatalogo.objects.get(concepto__codigo="TIPO_ITEM", codigo="MUEBLE_MEDIDA")

    # Pedido mixto: mueble + silla requiere OT TERMINADA
    pf_mix = crear_proforma(actor=encargado, moneda_codigo="BOB", titulo="Mixto OT", cliente=cli)
    det_m = agregar_detalle(
        proforma_id=pf_mix.id,
        actor=encargado,
        tipo_item=tipo_mueble,
        nombre="Mesa mixta",
        cantidad=Decimal("1"),
        unidad=unidad_pieza,
        precio_unitario=Decimal("900.00"),
    )
    crear_especificacion(
        detalle_id=det_m.id,
        actor=encargado,
        tipo_mueble=ValorCatalogo.objects.get(concepto__codigo="TIPO_MUEBLE", codigo="ESCRITORIO"),
        datos_tecnicos={"dimensiones": {"largo_mm": 1200, "ancho_mm": 600, "alto_mm": 750}},
    )
    agregar_detalle(
        proforma_id=pf_mix.id,
        actor=encargado,
        tipo_item=tipo_silla,
        producto=prod,
        nombre=prod.nombre,
        cantidad=Decimal("1"),
        unidad=unidad_pieza,
        precio_unitario=Decimal("400.00"),
    )
    enviar_proforma(proforma_id=pf_mix.id, actor=encargado)
    ped_mix = aprobar_proforma(proforma_id=pf_mix.id, actor=encargado)
    ot_mix = OrdenTrabajo.objects.get(pedido=ped_mix)
    with pytest.raises(ValidationError):
        cambiar_estado_pedido(pedido_id=ped_mix.id, actor=encargado, estado_codigo="LISTO_ENTREGA")
    cambiar_estado_orden_trabajo(orden_trabajo_id=ot_mix.id, actor=jefe, estado_codigo="EN_PROCESO")
    cambiar_estado_orden_trabajo(orden_trabajo_id=ot_mix.id, actor=jefe, estado_codigo="TERMINADA")
    ped_mix = cambiar_estado_pedido(
        pedido_id=ped_mix.id, actor=encargado, estado_codigo="LISTO_ENTREGA"
    )
    assert ped_mix.estado.codigo == "LISTO_ENTREGA"

    # Pedido solo catálogo pasa directo a LISTO_ENTREGA
    pf_cat = crear_proforma(actor=encargado, moneda_codigo="BOB", titulo="Solo silla", cliente=cli)
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
    ped_cat = cambiar_estado_pedido(
        pedido_id=ped_cat.id, actor=encargado, estado_codigo="LISTO_ENTREGA"
    )
    assert ped_cat.estado.codigo == "LISTO_ENTREGA"


@pytest.mark.django_db
def test_validacion_celular_y_direccion_clientes(django_user_model):
    encargado, _, _ = _crear_usuarios(django_user_model)
    api = APIClient()
    api.force_authenticate(user=encargado)

    tipo_persona = ValorCatalogo.objects.get(concepto__codigo="TIPO_CLIENTE", codigo="PERSONA")
    # Creación sin celular o dirección falla
    resp_bad = api.post(
        "/api/v1/clientes/",
        {
            "tipo_cliente": tipo_persona.id,
            "nombres": "Lucía",
            "apellidos": "Méndez",
            "celular": "123",
            "direccion": "",
        },
        format="json",
    )
    assert resp_bad.status_code == 400

    # Creación válida
    resp_ok = api.post(
        "/api/v1/clientes/",
        {
            "tipo_cliente": tipo_persona.id,
            "nombres": "Lucía",
            "apellidos": "Méndez",
            "celular": "71234567",
            "direccion": "Av. 6 de Agosto 2100",
        },
        format="json",
    )
    assert resp_ok.status_code == 201

    # Registro histórico incompleto se conserva pero bloquea formalización de pedido
    cli_hist = Cliente.objects.create(
        tipo_cliente=tipo_persona,
        nombres="Histórico",
        apellidos="SinDatos",
        celular="",
        direccion="",
        created_by=encargado,
        updated_by=encargado,
    )
    prod = silla(encargado, sku="SILLA-HIST-CLI", precio="300.00")
    cargar_stock(prod, encargado, Decimal("2"))
    unidad_pieza = ValorCatalogo.objects.get(concepto__codigo="UNIDAD_MEDIDA", codigo="PIEZA")
    tipo_silla = ValorCatalogo.objects.get(concepto__codigo="TIPO_ITEM", codigo="SILLA")
    pf = crear_proforma(actor=encargado, moneda_codigo="BOB", titulo="Borrador", cliente=cli_hist)
    agregar_detalle(
        proforma_id=pf.id,
        actor=encargado,
        tipo_item=tipo_silla,
        producto=prod,
        nombre=prod.nombre,
        cantidad=Decimal("1"),
        unidad=unidad_pieza,
        precio_unitario=Decimal("300.00"),
    )
    enviar_proforma(proforma_id=pf.id, actor=encargado)
    with pytest.raises(ValidationError):
        aprobar_proforma(proforma_id=pf.id, actor=encargado)

    # Cliente histórico con dirección pero celular inválido (!= 8 dígitos) también se bloquea
    cli_hist.celular = "12345"
    cli_hist.direccion = "Av. Arce 100"
    cli_hist.save(update_fields=["celular", "direccion"])
    pf.refresh_from_db()
    pf.cliente_celular_snapshot = "12345"
    pf.cliente_direccion_snapshot = "Av. Arce 100"
    pf.save(update_fields=["cliente_celular_snapshot", "cliente_direccion_snapshot"])
    with pytest.raises(ValidationError):
        aprobar_proforma(proforma_id=pf.id, actor=encargado)


@pytest.mark.django_db
def test_pdfs_usan_fecha_comercial_y_pie_demostracion_en_nota_y_recibo(django_user_model):
    import shutil
    import subprocess
    from datetime import date
    from uuid import uuid4

    from apps.core.tiempo_comercial import reloj_comercial_simulado
    from apps.documentos.pdf import (
        renderizar_nota_entrega_pdf,
        renderizar_orden_trabajo_pdf,
        renderizar_proforma_pdf,
    )
    from apps.documentos.pdf_recibo import renderizar_recibo_pdf
    from apps.proformas.models import RegistroProcedenciaImportacion
    from apps.recibos.services import emitir_recibo_idempotente

    encargado, jefe, _ = _crear_usuarios(django_user_model)
    cli = cliente_persona(encargado)

    with reloj_comercial_simulado(date(2026, 11, 5)):
        ped, ot = _crear_pedido_mueble(encargado, cli, titulo="PDF fechas y pie")
        pf = ped.proforma
        recibo, _ = emitir_recibo_idempotente(
            pedido=ped,
            actor=encargado,
            clave_idempotencia=str(uuid4()),
            nombre_completo="Ana Pérez",
            monto_en_letras="Cien 00/100 Bolivianos",
            concepto="Anticipo",
            tipo_pago=ValorCatalogo.objects.get(concepto__codigo="TIPO_PAGO", codigo="EFECTIVO"),
            pago_actual=Decimal("100.00"),
        )
        cambiar_estado_orden_trabajo(orden_trabajo_id=ot.id, actor=jefe, estado_codigo="EN_PROCESO")
        cambiar_estado_orden_trabajo(orden_trabajo_id=ot.id, actor=jefe, estado_codigo="TERMINADA")
        cambiar_estado_pedido(pedido_id=ped.id, actor=encargado, estado_codigo="LISTO_ENTREGA")
        nota = NotaEntrega.objects.get(pedido=ped)

    OrdenTrabajo.objects.filter(pk=ot.pk).update(fecha=date(2026, 11, 5))
    NotaEntrega.objects.filter(pk=nota.pk).update(fecha=date(2026, 11, 5))

    RegistroProcedenciaImportacion.objects.create(
        entidad="PROFORMA",
        source_id="TEST-SIM-PF",
        objeto_id=pf.id,
        naturaleza="SIMULADO_NO_RESULTADO_MEDIDO",
        payload_hash="a" * 64,
    )

    raw_pf = renderizar_proforma_pdf(pf.id, usuario=encargado)
    raw_ot = renderizar_orden_trabajo_pdf(ot.id, usuario=jefe)
    raw_ne = renderizar_nota_entrega_pdf(nota.id, usuario=encargado)
    raw_rec = renderizar_recibo_pdf(recibo.id, usuario=encargado)

    if shutil.which("pdftotext"):
        for raw in (raw_pf, raw_ot, raw_ne):
            txt = subprocess.check_output(["pdftotext", "-", "-"], input=raw).decode(
                "utf-8", errors="replace"
            )
            assert "Emisión: 5 de noviembre de 2026" in txt
            assert "Generado:" in txt
            assert "Documento de demostración (datos simulados)" in txt

        txt_rec = subprocess.check_output(["pdftotext", "-", "-"], input=raw_rec).decode(
            "utf-8", errors="replace"
        )
        assert "5 de noviembre de 2026" in txt_rec
        assert "Documento de demostración (datos simulados)" in txt_rec
    else:
        for raw in (raw_pf, raw_ot, raw_ne, raw_rec):
            assert raw.startswith(b"%PDF")
