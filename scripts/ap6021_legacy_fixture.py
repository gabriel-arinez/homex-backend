"""Fixture AP6.0.21 sólo para PostgreSQL descartable de CI.

Sembrar tras proformas.0008, antes de 0009; verificar después de 0010.
Incluye ficha histórica APROBADA y BORRADOR para probar actualización real.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.db import DatabaseError, connection, transaction  # noqa: E402

NUMEROS = (998621, 998622)


def _entorno_ci():
    if connection.settings_dict["NAME"] != "homex_test" or os.getenv(
        "DJANGO_SETTINGS_MODULE"
    ) != "config.settings.test":
        raise SystemExit("Fixture permitido únicamente en homex_test con settings.test.")


def _valor(concepto, codigo):
    with connection.cursor() as c:
        c.execute(
            """SELECT v.id FROM catalogo_valores v
               JOIN catalogo_conceptos t ON t.id=v.concepto_id
               WHERE t.codigo=%s AND v.codigo=%s""",
            [concepto, codigo],
        )
        return c.fetchone()[0]


def seed():
    _entorno_ci()
    usuario = get_user_model().objects.create_user(username="ap6021-legacy-approved-ci")
    bob = _valor("MONEDA", "BOB")
    borrador = _valor("ESTADO_PROFORMA", "BORRADOR")
    aprobada = _valor("ESTADO_PROFORMA", "APROBADA")
    mueble = _valor("TIPO_ITEM", "MUEBLE_MEDIDA")
    unidad = _valor("UNIDAD_MEDIDA", "PIEZA")
    with connection.cursor() as cursor:
        for indice, numero in enumerate(NUMEROS):
            cursor.execute(
                """INSERT INTO proformas(numero,vendedor_id,estado_id,moneda_id,fecha,
                        subtotal, descuento_total,total)
                   VALUES (%s,%s,%s,%s,%s,0,0,0) RETURNING id""",
                [numero, usuario.id, borrador, bob, date.today()],
            )
            proforma = cursor.fetchone()[0]
            cursor.execute(
                """INSERT INTO proformas_detalle(proforma_id,tipo_item_id,nombre,
                       cantidad,unidad_id,modo_calculo,precio_unitario,descuento)
                   VALUES (%s,%s,%s,1,%s,'PRECIO_UNITARIO',500,0)
                   RETURNING id""",
                [proforma, mueble, "Mueble histórico", unidad],
            )
            detalle = cursor.fetchone()[0]
            cursor.execute(
                """INSERT INTO especificaciones_mueble(
                      proforma_detalle_id,schema_version,espesor,color_principal,
                      dimensiones,accesorios,componentes,texto_original,advertencias,
                      observaciones)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                [
                    detalle, 2 if indice == 0 else 1,
                    '{"espesor":"18 mm"}', "Nogal", '{"ancho":"1.20 m"}',
                    '["Pasacables"]',
                    '[{"nombre":"Mesón","material":"Melamina"}]' if indice == 0 else '[]',
                    "Transcripción original inmutable",
                    '["color a elección"]' if indice == 0 else '[]',
                    "Conservar acabado",
                ],
            )
            if indice == 0:
                # Sólo el fixture CI simula la condición histórica APROBADA
                # evitando efectos secundarios del workflow de ventas.
                cursor.execute("ALTER TABLE proformas DISABLE TRIGGER USER")
                try:
                    cursor.execute(
                        "UPDATE proformas SET estado_id=%s WHERE id=%s",
                        [aprobada, proforma],
                    )
                finally:
                    cursor.execute("ALTER TABLE proformas ENABLE TRIGGER USER")
    print("ap6021-legacy-seed-ok approved=1 draft=1")


def verify():
    _entorno_ci()
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT p.numero, em.id, em.datos_tecnicos, em.observaciones, c.codigo
               FROM especificaciones_mueble em
               JOIN proformas_detalle pd ON pd.id=em.proforma_detalle_id
               JOIN proformas p ON p.id=pd.proforma_id
               JOIN catalogo_valores c ON c.id=p.estado_id
               WHERE p.numero IN (%s,%s) ORDER BY p.numero""",
            list(NUMEROS),
        )
        filas = cursor.fetchall()
        assert len(filas) == 2
        aprobado, borrador = filas
        assert aprobado[4] == "APROBADA"
        assert borrador[4] == "BORRADOR"
        for _, _, datos, observaciones, _ in filas:
            assert datos["descripcion_original"] == "Transcripción original inmutable"
            assert datos["caracteristicas_generales"]["color_principal"] == "Nogal"
            assert datos["caracteristicas_generales"]["dimensiones"] == {"ancho": "1.20 m"}
            assert datos["accesorios"] == ["Pasacables"]
            assert observaciones == "Conservar acabado"
        assert aprobado[2]["componentes"][0]["nombre"] == "Mesón"
        assert aprobado[2]["advertencias"] == ["color a elección"]
        cursor.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema=current_schema() AND table_name='especificaciones_mueble'"""
        )
        assert {x[0] for x in cursor.fetchall()} == {
            "id", "proforma_detalle_id", "tipo_mueble_id", "datos_tecnicos", "observaciones"
        }

    # La ventana excepcional de migración no puede dejar abierta la edición
    # de especificaciones ligadas a proformas aprobadas.
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE especificaciones_mueble SET observaciones='CAMBIO NO AUTORIZADO' WHERE id=%s",
                    [aprobado[1]],
                )
    except DatabaseError:
        pass
    else:
        raise AssertionError("PostgreSQL permitió editar una ficha APROBADA.")
    print("ap6021-legacy-upgrade-verified approved_immutable=1 preserved=2")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"seed", "verify"}:
        raise SystemExit("Uso: python scripts/ap6021_legacy_fixture.py seed|verify")
    {"seed": seed, "verify": verify}[sys.argv[1]]()
