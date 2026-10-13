"""Fixture reproducible CAJA/TOTAL_NEGOCIADO en PostgreSQL aislado.

Uso SOLO en el job postgres-migrations, nunca contra una base operativa.
Antes de seed migrar hasta proformas.0004 y movimientos_stock.0003.
Después de seed aplicar todas las migraciones AP6 y ejecutar verify.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.db import connection  # noqa: E402

SKU = "AP6-LEGACY-CAJA-CI"
NUMERO = 998610


def _catalogo(concepto: str, codigo: str) -> int:
    from apps.catalogo.models import ValorCatalogo

    return ValorCatalogo.objects.values_list("id", flat=True).get(
        concepto__codigo=concepto, codigo=codigo
    )


def seed() -> None:
    actor = get_user_model().objects.create_user(username="ap6-legacy-caja")
    unidad = _catalogo("UNIDAD_MEDIDA", "CAJA")
    categoria = _catalogo("CATEGORIA_PRODUCTO", "PISO_FLOTANTE")
    tipo = _catalogo("TIPO_ITEM", "PISO_FLOTANTE")
    borrador = _catalogo("ESTADO_PROFORMA", "BORRADOR")
    bob = _catalogo("MONEDA", "BOB")
    carga = _catalogo("TIPO_MOVIMIENTO", "CARGA_INICIAL")
    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO productos
                 (categoria_id, sku, nombre, precio_lista, stock, unidad_stock_id, activo)
                 VALUES (%s, %s, %s, %s, 0, %s, TRUE) RETURNING id""",
            [categoria, SKU, "Piso por caja histórico", "900.00", unidad],
        )
        producto = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO productos_piso (producto_id, m2_por_caja) VALUES (%s, %s)",
            [producto, "2.5000"],
        )
        cursor.execute(
            """INSERT INTO movimientos_stock
               (producto_id, fecha, tipo_movimiento_id, cantidad, observaciones)
               VALUES (%s, NOW(), %s, 5, %s)""",
            [producto, carga, "Carga histórica AP6 para prueba de migración"],
        )
        cursor.execute(
            """INSERT INTO proformas
               (numero, vendedor_id, estado_id, moneda_id, fecha)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            [NUMERO, actor.id, borrador, bob, date.today()],
        )
        proforma = cursor.fetchone()[0]
        cursor.execute(
            """INSERT INTO proformas_detalle
               (proforma_id, tipo_item_id, producto_id, nombre, cantidad,
                unidad_id, modo_calculo, precio_unitario, importe_negociado, descuento)
               VALUES (%s, %s, %s, %s, 2, %s, 'TOTAL_NEGOCIADO', 900.00, 1800.00, 0)""",
            [proforma, tipo, producto, SKU, unidad],
        )
    print("legacy-caja-seed-ok", producto, proforma)


def verify() -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT p.stock, u.codigo, pp.m2_por_caja,
                      (SELECT COALESCE(SUM(ms.cantidad), 0)
                       FROM movimientos_stock ms WHERE ms.producto_id = p.id)
               FROM productos p
               JOIN catalogo_valores u ON p.unidad_stock_id = u.id
               JOIN productos_piso pp ON pp.producto_id = p.id
               WHERE p.sku = %s""",
            [SKU],
        )
        stock, unidad, equivalencia, movimientos = cursor.fetchone()
        assert unidad == "CAJA"
        assert Decimal(stock) == Decimal("5.0000")
        assert Decimal(movimientos) == Decimal(stock)
        assert Decimal(equivalencia) == Decimal("2.5000")
        cursor.execute(
            """SELECT d.cantidad, u.codigo, d.modo_calculo, d.importe_negociado,
                      d.total, p.total, p.subtotal, p.descuento_total
               FROM proformas_detalle d
               JOIN proformas p ON d.proforma_id=p.id
               JOIN catalogo_valores u ON d.unidad_id=u.id
               WHERE p.numero=%s""",
            [NUMERO],
        )
        cantidad, unidad, modo, importe, total_linea, total, subtotal, descuento = (
            cursor.fetchone()
        )
        assert Decimal(cantidad) == Decimal("2.0000")
        assert unidad == "CAJA"
        assert modo == "TOTAL_NEGOCIADO"
        assert Decimal(importe) == Decimal("1800.00")
        assert Decimal(total_linea) == Decimal("1800.00")
        assert Decimal(total) == Decimal("1800.00")
        assert Decimal(subtotal) == Decimal("1800.00")
        assert Decimal(descuento) == Decimal("0.00")
    print("legacy-caja-migration-preserved-ok")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"seed", "verify"}:
        raise SystemExit("Uso: python scripts/ap6_legacy_caja_fixture.py [seed|verify]")
    if sys.argv[1] == "seed":
        seed()
    else:
        verify()
