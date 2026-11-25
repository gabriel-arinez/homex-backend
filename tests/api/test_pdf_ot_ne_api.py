"""Pruebas de integración y permisos para PDFs de Orden de Trabajo y Nota de Entrega."""

from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from apps.notas_entrega.services import emitir_nota
from apps.ordenes_trabajo.models import OrdenTrabajo
from apps.pedidos.services import aprobar_proforma
from apps.proformas.services import agregar_detalle, crear_proforma, enviar_proforma
from tests.factories import cargar_stock, cliente_persona, silla, valor, vendedor


def _jefe_taller(user):
    grupo, _ = Group.objects.get_or_create(name="JEFE_TALLER")
    user.groups.add(grupo)
    return user


def _avanzar_a_listo_entrega(pedido):
    from apps.ordenes_trabajo.models import OrdenTrabajo

    pedido.estado = valor("ESTADO_PEDIDO", "EN_PRODUCCION")
    pedido.save(update_fields=["estado"])
    for ot in OrdenTrabajo.objects.filter(pedido=pedido):
        ot.estado = valor("ESTADO_ORDEN_TRABAJO", "EN_PROCESO")
        ot.save(update_fields=["estado"])
        ot.estado = valor("ESTADO_ORDEN_TRABAJO", "TERMINADA")
        ot.save(update_fields=["estado"])
    pedido.estado = valor("ESTADO_PEDIDO", "LISTO_ENTREGA")
    pedido.save(update_fields=["estado"])
    pedido.refresh_from_db()


def _crear_pedido_con_mueble_y_silla(propietario):
    producto = silla(propietario, sku="PDF-OT-NE-SILLA")
    cargar_stock(producto, propietario, Decimal("5.0000"))

    proforma = crear_proforma(
        actor=propietario,
        cliente=cliente_persona(propietario),
        titulo="Proyecto Sala Reuniones",
    )
    agregar_detalle(
        proforma_id=proforma.id,
        actor=propietario,
        tipo_item=valor("TIPO_ITEM", "SILLA"),
        producto_id=producto.id,
        nombre=producto.nombre,
        cantidad=2,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("450.00"),
    )
    detalle_mueble = agregar_detalle(
        proforma_id=proforma.id,
        actor=propietario,
        tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
        nombre="Mesa Reuniones",
        descripcion="Mesa con estructura metálica",
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("2500.00"),
    )
    from apps.proformas.models import EspecificacionMueble

    EspecificacionMueble.objects.create(
        proforma_detalle=detalle_mueble,
        datos_tecnicos={
            "caracteristicas_generales": {"dimensiones": {"largo": {"valor": 200, "unidad": "cm"}}},
            "componentes": [{"nombre": "Base", "material": "Acero negro"}],
        },
        observaciones="Instalar niveladores.",
    )
    enviar_proforma(proforma_id=proforma.id, actor=propietario)
    pedido = aprobar_proforma(proforma_id=proforma.id, actor=propietario)
    orden = OrdenTrabajo.objects.get(pedido=pedido)
    from apps.catalogo.models import ConceptoCatalogo, ValorCatalogo

    concepto_saldo, _ = ConceptoCatalogo.objects.get_or_create(codigo="ESTADO_SALDO")
    estado_saldo_pendiente, _ = ValorCatalogo.objects.get_or_create(
        concepto=concepto_saldo, codigo="PENDIENTE", defaults={"nombre": "Pendiente"}
    )
    orden.responsable_recepcion = "Marco López"
    orden.lugar_entrega = "Calle 21 Calacoto"
    orden.estado_saldo = estado_saldo_pendiente
    orden.save(update_fields=["responsable_recepcion", "lugar_entrega", "estado_saldo"])
    return pedido, orden


@pytest.mark.django_db(transaction=True)
def test_orden_trabajo_pdf_permisos_y_contrato_http(django_user_model):
    propietario = vendedor(django_user_model.objects.create_user(username="ot-pdf-owner"))
    ajeno = vendedor(django_user_model.objects.create_user(username="ot-pdf-other"))
    jefe = _jefe_taller(django_user_model.objects.create_user(username="ot-pdf-jefe"))
    sin_rol = django_user_model.objects.create_user(username="ot-pdf-sin-rol")

    _, orden = _crear_pedido_con_mueble_y_silla(propietario)
    url = f"/api/v1/ordenes-trabajo/{orden.id}/documento-pdf/"
    api = APIClient()

    # Anónimo -> 401
    assert api.get(url).status_code == 401

    # Sin rol -> 403
    api.force_authenticate(sin_rol)
    assert api.get(url).status_code == 403

    # Vendedor ajeno -> 200 (lectura compartida)
    api.force_authenticate(ajeno)
    assert api.get(url).status_code == 200

    # Propietario y Jefe de Taller -> 200 PDF válido
    for actor in (propietario, jefe):
        api.force_authenticate(actor)
        resp = api.get(url)
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/pdf"
        assert (
            resp["Content-Disposition"]
            == f'attachment; filename="orden-trabajo-{orden.numero}.pdf"'
        )
        assert "no-store" in resp["Cache-Control"]
        assert "private" in resp["Cache-Control"]
        assert "Authorization" in resp["Vary"]
        assert resp.content.startswith(b"%PDF")


@pytest.mark.django_db(transaction=True)
def test_nota_entrega_pdf_permisos_y_contrato_http(django_user_model):
    propietario = vendedor(django_user_model.objects.create_user(username="ne-pdf-owner"))
    ajeno = vendedor(django_user_model.objects.create_user(username="ne-pdf-other"))
    jefe = _jefe_taller(django_user_model.objects.create_user(username="ne-pdf-jefe"))
    sin_rol = django_user_model.objects.create_user(username="ne-pdf-sin-rol")

    pedido, _ = _crear_pedido_con_mueble_y_silla(propietario)
    _avanzar_a_listo_entrega(pedido)
    nota = emitir_nota(pedido=pedido, actor=propietario)

    url = f"/api/v1/notas-entrega/{nota.id}/documento-pdf/"
    api = APIClient()

    # Anónimo -> 401
    assert api.get(url).status_code == 401

    # Jefe de Taller y usuario sin rol -> 403
    for unauthorized in (jefe, sin_rol):
        api.force_authenticate(unauthorized)
        assert api.get(url).status_code == 403

    # Vendedor ajeno -> 200 (lectura compartida)
    api.force_authenticate(ajeno)
    assert api.get(url).status_code == 200

    # Propietario -> 200 PDF válido
    api.force_authenticate(propietario)
    resp = api.get(url)
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    assert resp["Content-Disposition"] == f'attachment; filename="nota-entrega-{nota.numero}.pdf"'
    assert "no-store" in resp["Cache-Control"]
    assert "private" in resp["Cache-Control"]
    assert "Authorization" in resp["Vary"]
    assert resp.content.startswith(b"%PDF")
