"""Regresiones del documento editorial: no tocar cálculo ni estados."""

from decimal import Decimal
from unittest.mock import patch

import pytest
from reportlab.platypus import Paragraph

from apps.documentos.pdf import renderizar_proforma_pdf
from apps.proformas.models import EspecificacionMueble
from apps.proformas.services import agregar_detalle, crear_proforma
from tests.factories import cliente_persona, valor, vendedor


@pytest.mark.django_db(transaction=True)
def test_documento_editorial_sin_foto_sin_descuentos_ni_subtotal_repetido(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="editorial-pdf"))
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
        nombre="escritorio ejecutivo",
        descripcion="Escritorio de trabajo con repisas laterales.",
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("1450.00"),
        descuento=Decimal("0.00"),
    )
    EspecificacionMueble.objects.create(
        proforma_detalle=detalle,
        datos_tecnicos={
            "caracteristicas_generales": {"material": "Melamina"},
            "componentes": [{"nombre": "Repisas", "material": "Melamina"}],
        },
        observaciones="Sin cajones.",
    )
    with patch("apps.documentos.pdf.Paragraph", wraps=Paragraph) as parrafos:
        pdf = renderizar_proforma_pdf(proforma.id)

    textos = [call.args[0] for call in parrafos.call_args_list if call.args]
    assert pdf.startswith(b"%PDF")
    assert b"/MediaBox [ 0 0 612 792 ]" in pdf
    assert any("TOTAL COTIZADO" in str(texto) for texto in textos)
    assert not any("Subtotal general" in str(texto) for texto in textos)
    assert not any("Descuento global" in str(texto) for texto in textos)
    assert not any("Imagen de referencia pendiente" in str(texto) for texto in textos)
    assert any("Aceptación y aprobación comercial" in str(texto) for texto in textos)
    assert any("escritorio ejecutivo" in str(texto).lower() for texto in textos)
