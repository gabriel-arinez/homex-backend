"""Regresiones del esquema final AP6.0.21.

La conversión desde 0008 (incluidas fichas APROBADAS y V1/V2) se prueba
mediante scripts/ap6021_legacy_fixture.py en el job postgres-migrations.
Nunca revertir una BD de tests con datos JSONB a 0008: perdería columnas.
"""
import pytest
from django.db import connection
from django.db.migrations.exceptions import IrreversibleError
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_ap6021_tabla_unica_y_trigger_activo():
    with connection.cursor() as cursor:
        columnas = {
            columna.name
            for columna in connection.introspection.get_table_description(
                cursor, "especificaciones_mueble"
            )
        }
        cursor.execute(
            """SELECT tgenabled FROM pg_trigger
               WHERE tgrelid='especificaciones_mueble'::regclass
                 AND tgname='trg_bloquear_especificacion_aprobada'"""
        )
        trigger = cursor.fetchone()
    assert columnas == {
        "id",
        "proforma_detalle_id",
        "tipo_mueble_id",
        "datos_tecnicos",
        "observaciones",
    }
    assert trigger == ("O",)


@pytest.mark.django_db(transaction=True)
def test_ap6021_reversion_no_puede_eliminar_json_comercial():
    executor = MigrationExecutor(connection)
    migracion = executor.loader.disk_migrations[
        ("proformas", "0010_ap6021_validacion_y_rollback_seguro")
    ]
    bloqueo_reversion = migracion.operations[-1]
    with pytest.raises(IrreversibleError, match="rollback Django"):
        bloqueo_reversion.reverse_code(None, None)
