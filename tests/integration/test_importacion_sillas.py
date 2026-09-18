import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalogo.models import ConceptoCatalogo, Producto, ProductoSilla, ValorCatalogo
from apps.movimientos_stock.models import MovimientoStock


@pytest.fixture
def import_catalog():
    values = {}
    for concepto_codigo, codes in {
        "CATEGORIA_PRODUCTO": {"SILLA": "Silla"},
        "UNIDAD_MEDIDA": {"PIEZA": "Pieza"},
        "TIPO_MOVIMIENTO": {"CARGA_INICIAL": "Carga inicial"},
        "MARCA": {"HOMEX": "HOMEX"},
        "COLOR": {"NEGRO": "Negro", "GRIS": "Gris"},
    }.items():
        concepto = ConceptoCatalogo.objects.create(codigo=concepto_codigo)
        for codigo, nombre in codes.items():
            values[(concepto_codigo, codigo)] = ValorCatalogo.objects.create(
                concepto=concepto, codigo=codigo, nombre=nombre
            )
    return values


def write_rows(tmp_path, rows):
    input_path = tmp_path / "sillas.json"
    input_path.write_text(json.dumps(rows), encoding="utf-8")
    return input_path


@pytest.mark.django_db
def test_chair_import_is_dry_run_then_idempotent(tmp_path, import_catalog):
    input_path = write_rows(
        tmp_path,
        [
            {
                "sku": "B15-NEGRO",
                "nombre": "Silla B15 negra",
                "precio_lista": "1500.00",
                "stock": 3,
                "marca_codigo": "HOMEX",
                "modelo": "B15",
                "color_primario_codigo": "NEGRO",
                "color_secundario_codigo": "GRIS",
                "especificaciones": {"material": "malla"},
            }
        ],
    )
    output = StringIO()
    call_command("import_sillas", input=str(input_path), dry_run=True, stdout=output)
    assert "creados=1" in output.getvalue()
    assert Producto.objects.count() == 0

    call_command("import_sillas", input=str(input_path), stdout=output)
    producto = Producto.objects.get(sku="B15-NEGRO")
    assert producto.stock == 3
    assert ProductoSilla.objects.get(producto=producto).modelo == "B15"
    assert MovimientoStock.objects.get(producto=producto).tipo_movimiento.codigo == "CARGA_INICIAL"

    call_command("import_sillas", input=str(input_path), stdout=output)
    assert Producto.objects.count() == 1
    assert MovimientoStock.objects.filter(producto=producto).count() == 1
    assert "omitidos=1" in output.getvalue()


@pytest.mark.django_db
def test_chair_import_rejects_missing_commercial_identity(tmp_path, import_catalog):
    input_path = write_rows(tmp_path, [{"text": "Silla Ejecutiva", "label": []}])
    with pytest.raises(CommandError, match="no se aplicó"):
        call_command("import_sillas", input=str(input_path), dry_run=True)
    assert Producto.objects.count() == 0


@pytest.mark.django_db
def test_catalog_price_and_reference_availability(import_catalog):
    from datetime import date
    from decimal import Decimal

    from apps.catalogo.consultas import disponibilidad_producto, precio_producto
    from apps.catalogo.models import DescuentoProducto
    from apps.proformas.models import DetalleProforma, Proforma

    estado_concepto = ConceptoCatalogo.objects.create(codigo="ESTADO_PROFORMA")
    sent = ValorCatalogo.objects.create(concepto=estado_concepto, codigo="ENVIADA", nombre="Enviada")
    moneda_concepto = ConceptoCatalogo.objects.create(codigo="MONEDA")
    bob = ValorCatalogo.objects.create(concepto=moneda_concepto, codigo="BOB", nombre="Boliviano")
    cliente_concepto = ConceptoCatalogo.objects.create(codigo="TIPO_CLIENTE")
    person = ValorCatalogo.objects.create(concepto=cliente_concepto, codigo="PERSONA", nombre="Persona")
    item_concepto = ConceptoCatalogo.objects.create(codigo="TIPO_ITEM")
    chair_item = ValorCatalogo.objects.create(concepto=item_concepto, codigo="SILLA", nombre="Silla")
    from django.contrib.auth import get_user_model

    from apps.clientes.models import Cliente

    vendedor = get_user_model().objects.create_user(username="availability-vendedor")
    cliente = Cliente.objects.create(tipo_cliente=person, nombres="Cliente")
    producto = Producto.objects.create(
        sku="B15-NEGRO",
        categoria=import_catalog[("CATEGORIA_PRODUCTO", "SILLA")],
        nombre="Silla B15",
        precio_lista=Decimal(1500),
        stock=8,
        unidad_stock=import_catalog[("UNIDAD_MEDIDA", "PIEZA")],
    )
    proforma = Proforma.objects.create(cliente=cliente, vendedor=vendedor, estado=sent, moneda=bob)
    DetalleProforma.objects.create(
        proforma=proforma,
        tipo_item=chair_item,
        producto=producto,
        nombre="Silla B15",
        cantidad=3,
        unidad=import_catalog[("UNIDAD_MEDIDA", "PIEZA")],
        precio_unitario=Decimal(1500),
    )
    DescuentoProducto.objects.create(
        producto=producto,
        precio_antes=Decimal(1500),
        precio_ahora=Decimal(1200),
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
    )

    assert disponibilidad_producto(producto).reference_availability == 5
    assert precio_producto(producto, on_date=date(2026, 6, 1)).effective_price == Decimal(1200)
