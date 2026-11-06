from django.db import migrations


def desactivar_estados(apps, schema_editor):
    valor = apps.get_model("catalogo", "ValorCatalogo")
    valor.objects.using(schema_editor.connection.alias).filter(
        concepto__codigo="ESTADO_PROFORMA", codigo__in=["ENVIADA", "RECHAZADA"]
    ).update(activo=False)


class Migration(migrations.Migration):
    dependencies = [
        ("proformas", "0012_proforma_creado_en"),
        ("catalogo", "0003_datos_iniciales"),
    ]

    operations = [migrations.RunPython(desactivar_estados, migrations.RunPython.noop)]
