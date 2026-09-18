from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.catalogo.models import ConceptoCatalogo, ValorCatalogo
from apps.clientes.models import Cliente
from apps.proformas.models import DetalleProforma, Proforma
from apps.proformas.servicios import recalcular_proforma


@pytest.mark.django_db
def test_negotiated_total_is_authoritative() -> None:
    concepto = ConceptoCatalogo.objects.create(codigo="BASE")
    state = ValorCatalogo.objects.create(concepto=concepto, codigo="BORRADOR", nombre="Borrador")
    moneda = ValorCatalogo.objects.create(concepto=concepto, codigo="BOB", nombre="Boliviano")
    tipo_item = ValorCatalogo.objects.create(concepto=concepto, codigo="MUEBLE_MEDIDA", nombre="Mueble")
    unidad = ValorCatalogo.objects.create(concepto=concepto, codigo="PIEZA", nombre="Pieza")
    tipo_cliente = ValorCatalogo.objects.create(concepto=concepto, codigo="PERSONA", nombre="Persona")
    user = get_user_model().objects.create_user(username="vendedor")
    cliente = Cliente.objects.create(
        tipo_cliente=tipo_cliente, nombres="Ana", apellidos="Lopez"
    )
    proforma = Proforma.objects.create(
        cliente=cliente, vendedor=user, estado=state, moneda=moneda
    )
    DetalleProforma.objects.create(
        proforma=proforma,
        tipo_item=tipo_item,
        nombre="Mueble",
        cantidad=3,
        unidad=unidad,
        modo_calculo="TOTAL_NEGOCIADO",
        monto_negociado=Decimal("100.00"),
    )
    proforma = recalcular_proforma(proforma.id)
    assert proforma.total == Decimal("100.00")


@pytest.mark.django_db
def test_precio_unitario_calculation_is_distinct() -> None:
    concepto = ConceptoCatalogo.objects.create(codigo="BASE")
    values = {
        codigo: ValorCatalogo.objects.create(concepto=concepto, codigo=codigo, nombre=codigo)
        for codigo in ("BORRADOR", "BOB", "MUEBLE_MEDIDA", "PIEZA", "PERSONA")
    }
    user = get_user_model().objects.create_user(username="vendedor")
    cliente = Cliente.objects.create(
        tipo_cliente=values["PERSONA"], nombres="Ana", apellidos="Lopez"
    )
    proforma = Proforma.objects.create(
        cliente=cliente, vendedor=user, estado=values["BORRADOR"], moneda=values["BOB"]
    )
    DetalleProforma.objects.create(
        proforma=proforma,
        tipo_item=values["MUEBLE_MEDIDA"],
        nombre="Mueble",
        cantidad=2,
        unidad=values["PIEZA"],
        precio_unitario=Decimal("50.00"),
        descuento=Decimal("5.00"),
    )
    assert recalcular_proforma(proforma.id).total == Decimal("95.00")


@pytest.mark.django_db
def test_submit_freezes_cliente_snapshot() -> None:
    from apps.proformas.servicios import enviar_proforma

    concepto = ConceptoCatalogo.objects.create(codigo="BASE")
    values = {
        codigo: ValorCatalogo.objects.create(concepto=concepto, codigo=codigo, nombre=codigo)
        for codigo in ("BORRADOR", "ENVIADA", "BOB", "PERSONA")
    }
    user = get_user_model().objects.create_user(username="vendedor")
    cliente = Cliente.objects.create(
        tipo_cliente=values["PERSONA"], nombres="Ana", apellidos="Lopez", celular="70000000"
    )
    proforma = Proforma.objects.create(
        cliente=cliente, vendedor=user, estado=values["BORRADOR"], moneda=values["BOB"]
    )
    submitted = enviar_proforma(proforma.id, user.id)
    assert submitted.estado.codigo == "ENVIADA"
    assert submitted.cliente_nombre_snapshot == "Ana Lopez"
    cliente.nombres = "Cambio"
    cliente.save()
    assert Proforma.objects.get(pk=proforma.id).cliente_nombre_snapshot == "Ana Lopez"
