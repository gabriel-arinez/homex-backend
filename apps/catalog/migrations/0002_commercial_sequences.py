from django.db import migrations

SEQUENCES = (
    "seq_proformas_numero",
    "seq_ordenes_trabajo_numero",
    "seq_notas_entrega_numero",
    "seq_recibos_numero",
)


def create_sequences(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for name in SEQUENCES:
        schema_editor.execute(f"CREATE SEQUENCE {name} START WITH 1 INCREMENT BY 1")


def drop_sequences(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for name in SEQUENCES:
        schema_editor.execute(f"DROP SEQUENCE {name}")


class Migration(migrations.Migration):
    dependencies = [("catalog", "0001_initial")]
    operations = [migrations.RunPython(create_sequences, drop_sequences)]
