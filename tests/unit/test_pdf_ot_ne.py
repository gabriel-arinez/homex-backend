"""Pruebas unitarias para PDFs de Orden de Trabajo y Nota de Entrega."""

from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import pytest
from PIL import Image as PILImage
from reportlab.platypus import Image as PdfImage
from reportlab.platypus import Paragraph

from apps.documentos.pdf import (
    renderizar_nota_entrega_pdf,
    renderizar_orden_trabajo_pdf,
)


def _actor(name="Carlos Taller"):
    return NS(is_authenticated=True, get_full_name=lambda: name, get_username=lambda: "carlos")


def _proforma(details=(), **changes):
    fields = dict(
        id=10,
        numero=405,
        fecha=date(2026, 11, 10),
        titulo="Mobiliario Gerencial",
        estado=NS(codigo="APROBADA", nombre="Aprobada"),
        moneda=NS(codigo="BOB"),
        cliente_id=None,
        cliente_nombre_snapshot="Laura Méndez",
        cliente_empresa_snapshot="Grupo Andino S.R.L.",
        cliente_celular_snapshot="70000000",
        cliente_direccion_snapshot="Av. Principal 123",
        prospecto_nombre=None,
        prospecto_empresa=None,
        prospecto_celular=None,
        prospecto_direccion=None,
        vendedor=_actor("Vendedor Original"),
        detalles=NS(all=lambda: list(details)),
        total=Decimal("8400.00"),
        subtotal=Decimal("8600.00"),
        descuento_total=Decimal("200.00"),
        observaciones="Validez sujeta a stock.",
        porcentaje_adelanto=Decimal("40"),
        plazo_entrega="15 días hábiles",
        validez_oferta=10,
    )
    fields.update(changes)
    return NS(**fields)


def _mueble_line(pk=1, **changes):
    datos = {
        "caracteristicas_generales": {
            "dimensiones": {
                "largo": {"valor": 220, "unidad": "cm"},
                "ancho": {"valor": 90, "unidad": "cm"},
                "alto": {"valor": 75, "unidad": "cm"},
            },
            "material_principal": "Melamina 18 mm",
        },
        "componentes": [
            {
                "uid": "comp-1",
                "nombre": "Tapa superior",
                "material": "Melamina roble",
                "espesor": {"valor": 36, "unidad": "mm"},
            }
        ],
        "accesorios": [
            {"componente_uid": "comp-1", "nombre": "Pasacables metálico", "cantidad": 2}
        ],
        "observaciones": "Canto PVC 2 mm en todo el perímetro.",
    }
    fields = dict(
        pk=pk,
        nombre="Mesa de Directorio",
        descripcion="Mesa ejecutiva con canaleta oculta.",
        producto_id=None,
        familia_producto_id=None,
        tipo_item_id=1,
        tipo_item=NS(codigo="MUEBLE_MEDIDA", nombre="Mueble a medida"),
        cantidad=Decimal("2"),
        unidad=NS(nombre="Pieza"),
        modo_calculo="PRECIO_UNITARIO",
        precio_unitario=Decimal("4300.00"),
        importe_negociado=None,
        descuento=Decimal("200.00"),
        total=Decimal("8400.00"),
        especificacionmueble=NS(
            datos_tecnicos=datos,
            observaciones="Verificar nivelación en sitio.",
            tipo_mueble_id=None,
        ),
    )
    fields.update(changes)
    return NS(**fields)


def _silla_line(pk=2):
    producto = NS(
        sku="SIL-ERGO-01",
        nombre="Silla Ergonómica Pro",
        familia=NS(nombre="Sillas Ejecutivas"),
        categoria=NS(codigo="SILLA"),
        unidad_stock=NS(nombre="Pieza"),
        observaciones="Garantía de 2 años en pistón.",
        productosilla=NS(
            marca=NS(nombre="Ergoline"),
            modelo="Pro-X",
            color_primario=NS(nombre="Negro"),
            color_secundario=NS(nombre="Gris"),
            especificaciones={"mecanismo": "Sincrónico", "base": "Aluminio 5 puntas"},
        ),
    )
    return NS(
        pk=pk,
        nombre="Silla Ergonómica Pro",
        descripcion="Con apoyo lumbar regulable.",
        producto_id=50,
        producto=producto,
        familia_producto_id=None,
        tipo_item_id=2,
        tipo_item=NS(codigo="SILLA", nombre="Silla"),
        cantidad=Decimal("4"),
        unidad=NS(nombre="Pieza"),
        modo_calculo="PRECIO_UNITARIO",
        precio_unitario=Decimal("950.00"),
        importe_negociado=None,
        descuento=Decimal("0"),
        total=Decimal("3800.00"),
        especificacionmueble=None,
    )


def _sample_image(_detail):
    stream = BytesIO()
    PILImage.new("RGB", (120, 80), color=(185, 28, 28)).save(stream, format="JPEG")
    stream.seek(0)
    return PdfImage(stream, width=40, height=27)


def _render_ot(orden, requester=None, image_factory=None):
    query = Mock()
    query.select_related.return_value = query
    query.prefetch_related.return_value = query
    query.get.return_value = orden
    texts = []

    def paragraph(value, *args, **kwargs):
        texts.append(value)
        return Paragraph(value, *args, **kwargs)

    with (
        patch("apps.documentos.pdf.OrdenTrabajo.objects", query),
        patch(
            "apps.documentos.pdf._imagen_principal_detalle",
            side_effect=image_factory or (lambda _: None),
        ),
        patch("apps.documentos.pdf.Paragraph", side_effect=paragraph),
    ):
        pdf = renderizar_orden_trabajo_pdf(orden.id, usuario=requester or _actor())
    return pdf, "\n".join(texts)


def _render_ne(nota, requester=None, image_factory=None):
    query = Mock()
    query.select_related.return_value = query
    query.prefetch_related.return_value = query
    query.get.return_value = nota
    texts = []

    def paragraph(value, *args, **kwargs):
        texts.append(value)
        return Paragraph(value, *args, **kwargs)

    with (
        patch("apps.documentos.pdf.NotaEntrega.objects", query),
        patch(
            "apps.documentos.pdf._imagen_principal_detalle",
            side_effect=image_factory or (lambda _: None),
        ),
        patch("apps.documentos.pdf.Paragraph", side_effect=paragraph),
    ):
        pdf = renderizar_nota_entrega_pdf(nota.id, usuario=requester or _actor())
    return pdf, "\n".join(texts)


def test_orden_trabajo_pdf_requires_authenticated_user():
    with pytest.raises(PermissionError):
        renderizar_orden_trabajo_pdf(1, usuario=NS(is_authenticated=False))


def test_nota_entrega_pdf_requires_authenticated_user():
    with pytest.raises(PermissionError):
        renderizar_nota_entrega_pdf(1, usuario=NS(is_authenticated=False))


def test_orden_trabajo_pdf_preserves_specs_and_excludes_all_financials():
    proforma = _proforma([_mueble_line(1), _silla_line(2)])
    orden = NS(
        id=77,
        numero=120,
        fecha=date(2026, 11, 12),
        pedido_id=33,
        pedido=NS(
            id=33, proforma=proforma, estado=NS(codigo="EN_PRODUCCION", nombre="En producción")
        ),
        estado=NS(codigo="EN_PROCESO", nombre="En proceso"),
        estado_saldo=NS(codigo="PARCIAL", nombre="Parcial"),
        responsable_recepcion="Ing. Roberto Paz",
        fecha_entrega=date(2026, 11, 25),
        lugar_entrega="Edificio Torres del Sur, Piso 4",
        jefe_taller=_actor(),
    )
    pdf, text = _render_ot(orden, image_factory=_sample_image)

    from django.utils import timezone

    from apps.documentos.pdf import _spanish_date

    assert pdf.startswith(b"%PDF")
    assert b"/MediaBox [ 0 0 612 792 ]" in pdf
    assert "Orden de trabajo" in text
    assert "N.º 120" in text
    assert _spanish_date(timezone.localdate()) in text
    assert "Grupo Andino S.R.L." in text
    assert "Pedido #33 · Proforma #405" in text
    assert "En proceso" in text
    assert "Ing. Roberto Paz" in text
    assert "25 de noviembre de 2026" in text
    assert "Edificio Torres del Sur, Piso 4" in text
    assert "Mobiliario Gerencial" in text

    # Especificaciones técnicas y catálogo completos
    assert "Mesa de Directorio" in text
    assert "Melamina 18 mm" in text
    assert "TAPA SUPERIOR" in text
    assert "Pasacables metálico" in text
    assert "Canto PVC 2 mm en todo el perímetro." in text
    assert "Verificar nivelación en sitio." in text
    assert "SIL-ERGO-01" in text
    assert "Sincrónico" in text
    assert "2 Pieza" in text
    assert "4 Pieza" in text

    # Exclusión absoluta de importes financieros y estado_saldo
    for forbidden in (
        "PRECIO UNITARIO",
        "SUBTOTAL",
        "DESCUENTO",
        "TOTAL COTIZADO",
        "4.300,00",
        "8.400,00",
        "950,00",
        "3.800,00",
        "ANTICIPO REQUERIDO",
        "VALIDEZ DE LA OFERTA",
        "Parcial",
        "estado_saldo",
    ):
        assert forbidden not in text


def test_orden_trabajo_pdf_handles_optional_fields_and_multipage_specs():
    long_components = [
        {
            "uid": f"c-{i}",
            "nombre": f"Módulo {i}",
            "material": "Melamina grafito 18 mm",
            "acabado": "Canto ABS 2 mm",
            "observaciones": f"Detalle constructivo extenso número {i} con refuerzo interno.",
        }
        for i in range(1, 25)
    ]
    line = _mueble_line(
        1,
        especificacionmueble=NS(
            datos_tecnicos={"componentes": long_components},
            observaciones="Ficha extensa multipágina.",
            tipo_mueble_id=None,
        ),
    )
    proforma = _proforma([line], titulo=None)
    orden = NS(
        id=78,
        numero=121,
        fecha=date(2026, 11, 13),
        pedido_id=34,
        pedido=NS(id=34, proforma=proforma, estado=NS(codigo="CONFIRMADO", nombre="Confirmado")),
        estado=NS(codigo="PENDIENTE", nombre="Pendiente"),
        estado_saldo=None,
        responsable_recepcion=None,
        fecha_entrega=None,
        lugar_entrega=None,
        jefe_taller=None,
    )
    pdf, text = _render_ot(orden)
    assert pdf.startswith(b"%PDF")
    assert "MÓDULO 1" in text
    assert "MÓDULO 24" in text
    assert "RESPONSABLE DE RECEPCIÓN" not in text
    assert "LUGAR DE ENTREGA" not in text
    # Verifica múltiples páginas
    assert b"/Count " in pdf


def test_nota_entrega_pdf_preserves_specs_persisted_amounts_and_reception_section():
    proforma = _proforma(
        [_mueble_line(1), _silla_line(2)],
        total=Decimal("12200.00"),
    )
    nota = NS(
        id=91,
        numero=501,
        fecha=date(2026, 11, 18),
        pedido_id=33,
        pedido=NS(
            id=33, proforma=proforma, estado=NS(codigo="LISTO_ENTREGA", nombre="Listo para entrega")
        ),
        vendedor=_actor("Ana Vendedora"),
    )
    pdf, text = _render_ne(nota, image_factory=_sample_image)

    from django.utils import timezone

    from apps.documentos.pdf import _spanish_date

    assert pdf.startswith(b"%PDF")
    assert b"/MediaBox [ 0 0 612 792 ]" in pdf
    assert "Nota de entrega" in text
    assert "N.º 501" in text
    assert _spanish_date(timezone.localdate()) in text
    assert "Grupo Andino S.R.L." in text
    assert "Pedido #33 · Proforma #405" in text
    assert "Entrega total" in text
    assert "Mobiliario Gerencial" in text

    # Fichas técnicas + importes persistidos
    assert "Melamina 18 mm" in text
    assert "SIL-ERGO-01" in text
    assert "Bs 4.300,00" in text
    assert "Bs 200,00" in text
    assert "Bs 8.400,00" in text
    assert "Bs 950,00" in text
    assert "Bs 3.800,00" in text
    assert "TOTAL ENTREGADO" in text
    assert "Bs 12.200,00" in text

    # Condiciones propias de cotización eliminadas
    assert "VALIDEZ DE LA OFERTA" not in text
    assert "ANTICIPO REQUERIDO" not in text
    assert "CONDICIONES COMERCIALES" not in text

    # Constancia de entrega y recepción sin firmas ficticias
    assert "CONSTANCIA DE ENTREGA Y RECEPCIÓN" in text
    assert "Entregado por" in text
    assert "Recibido por" in text
    assert "Ana Vendedora" not in text
    assert "Laura Méndez" not in text
