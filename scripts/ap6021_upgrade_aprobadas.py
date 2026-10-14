"""Actualizar AP6.0.21 con fichas APROBADAS, preservando triggers y registros.

NO se ejecuta automáticamente en ningún entorno. Requiere backup PostgreSQL
verificado y frase explícita. Probar sobre una copia aislada antes de producción.

Uso: uv run python scripts/ap6021_upgrade_aprobadas.py
       --backup /ruta/backup.dump --sha256 HASH
       --expected-database homex_test --confirm AP6021-UPGRADE-CONTROLADO
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

import django  # noqa: E402

django.setup()

from django.db import connection, transaction  # noqa: E402
from django.db.migrations.executor import MigrationExecutor  # noqa: E402

DESTINO = ("proformas", "0010_ap6021_validacion_y_rollback_seguro")
ORIGEN = ("proformas", "0008_ap6_caja_historica_stock")
PRIMERA = ("proformas", "0009_datos_tecnicos_unicos_ap6021")
CONFIRMACION = "AP6021-UPGRADE-CONTROLADO"


def consolidar_fila(fila):
    _, componentes, accesorios, original, advertencias, espesor, color1, color2, dimensiones = fila
    datos = {}
    if componentes:
        datos["componentes"] = componentes
    if accesorios:
        datos["accesorios"] = accesorios
    if original:
        datos["descripcion_original"] = original
    if advertencias:
        datos["advertencias"] = advertencias
    generales = {}
    for clave, valor in (
        ("espesor", espesor), ("color_principal", color1),
        ("color_secundario", color2), ("dimensiones", dimensiones),
    ):
        if valor not in (None, "", [], {}):
            generales[clave] = valor
    if generales:
        datos["caracteristicas_generales"] = generales
    return datos


def validar_backup(ruta: Path, sha256: str):
    if not ruta.is_file() or ruta.stat().st_size == 0:
        raise RuntimeError("El respaldo indicado no existe o está vacío.")
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    if h.hexdigest().lower() != sha256.lower():
        raise RuntimeError("El respaldo no coincide con el SHA-256 esperado.")
    print("backup-sha256-ok", h.hexdigest())


def ejecutar():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.confirm != CONFIRMACION:
        raise SystemExit("Confirmación inválida; no se aplicaron migraciones.")
    if connection.vendor != "postgresql":
        raise SystemExit("AP6.0.21 requiere PostgreSQL.")
    connection.ensure_connection()
    nombre_db = connection.settings_dict["NAME"]
    if nombre_db != args.expected_database:
        raise SystemExit(
            "La base conectada no coincide con --expected-database; se aborta."
        )
    validar_backup(args.backup, args.sha256)

    executor = MigrationExecutor(connection)
    aplicadas = executor.loader.applied_migrations
    if PRIMERA in aplicadas:
        raise SystemExit(
            "La migración 0009 ya fue aplicada. Usar migrate normal para 0010; "
            "nunca volver a ejecutar la consolidación heredada."
        )
    if ORIGEN not in aplicadas:
        raise SystemExit(
            "La base no está en proformas.0008; completar las migraciones "
            "previas o restaurar una copia compatible."
        )

    # DDL de desactivación y activación es transaccional en PostgreSQL.
    # ALTER TABLE toma un bloqueo exclusivo: no pueden entrar escrituras
    # concurrentes mientras la protección esté temporalmente deshabilitada.
    # Si falla una operación, el rollback revierte TODO, incluido el trigger.
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT id, componentes, accesorios, texto_original,
                          advertencias, espesor, color_principal, color_secundario,
                          dimensiones
                   FROM especificaciones_mueble ORDER BY id"""
            )
            esperado = {fila[0]: consolidar_fila(fila) for fila in cursor.fetchall()}
            cursor.execute(
                """SELECT COUNT(*)
                   FROM especificaciones_mueble em
                   JOIN proformas_detalle pd ON pd.id=em.proforma_detalle_id
                   JOIN proformas p ON p.id=pd.proforma_id
                   JOIN catalogo_valores c ON c.id=p.estado_id
                   WHERE c.codigo='APROBADA'"""
            )
            aprobadas = cursor.fetchone()[0]
            print(
                "ap6021-upgrade-preflight",
                f"database={nombre_db}",
                f"fichas={len(esperado)}",
                f"aprobadas={aprobadas}",
            )
            cursor.execute(
                """ALTER TABLE especificaciones_mueble
                   DISABLE TRIGGER trg_bloquear_especificacion_aprobada"""
            )

        executor = MigrationExecutor(connection)
        executor.migrate([DESTINO])

        with connection.cursor() as cursor:
            cursor.execute(
                """ALTER TABLE especificaciones_mueble
                   ENABLE TRIGGER trg_bloquear_especificacion_aprobada"""
            )
            cursor.execute(
                "SELECT id, datos_tecnicos FROM especificaciones_mueble ORDER BY id"
            )
            obtenido = dict(cursor.fetchall())
            if obtenido != esperado:
                raise RuntimeError(
                    "La consolidación difiere de la evidencia heredada; "
                    "se aborta y revierte toda la transacción."
                )
            cursor.execute(
                """SELECT tgenabled FROM pg_trigger
                   WHERE tgrelid='especificaciones_mueble'::regclass
                     AND tgname='trg_bloquear_especificacion_aprobada'"""
            )
            estado = cursor.fetchone()
            if estado != ("O",):
                raise RuntimeError("El trigger de inmutabilidad no quedó activo.")
            cursor.execute(
                """SELECT COUNT(*) FROM django_migrations
                   WHERE app='proformas'
                     AND name='0010_ap6021_validacion_y_rollback_seguro'"""
            )
            if cursor.fetchone()[0] != 1:
                raise RuntimeError("0010 no quedó registrada; se revierte.")
    print("ap6021-upgrade-ok", f"fichas_preservadas={len(esperado)}")


if __name__ == "__main__":
    ejecutar()
