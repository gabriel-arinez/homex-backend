from django.db import migrations


def ordenar(apps, schema_editor):
    Archivo = apps.get_model("documentos", "ArchivoAdjunto")
    detalles = Archivo.objects.exclude(proforma_detalle_id=None).values_list("proforma_detalle_id", flat=True).distinct()
    for detalle in detalles:
        for position, image in enumerate(Archivo.objects.filter(proforma_detalle_id=detalle).order_by("id")):
            image.posicion = position
            image.principal = position == 0
            image.save(update_fields=["posicion", "principal"])


class Migration(migrations.Migration):
    dependencies = [("documentos", "0007_proteger_adjuntos_existentes")]
    operations = [migrations.RunPython(ordenar, migrations.RunPython.noop)]
