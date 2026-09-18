from django.db import migrations

SECUENCIAS = (
    "seq_proformas_numero",
    "seq_ordenes_trabajo_numero",
    "seq_notas_entrega_numero",
    "seq_recibos_numero",
)


def crear(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        for nombre in SECUENCIAS:
            schema_editor.execute(f"CREATE SEQUENCE {nombre} START WITH 1 INCREMENT BY 1")


def eliminar(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        for nombre in SECUENCIAS:
            schema_editor.execute(f"DROP SEQUENCE IF EXISTS {nombre}")


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0001_initial")]
    operations = [migrations.RunPython(crear, eliminar)]
