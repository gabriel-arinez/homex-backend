from django.db import migrations


def conservar(apps, schema_editor):
    Producto = apps.get_model("catalogo", "Producto")
    Imagen = apps.get_model("catalogo", "ImagenProducto")
    for p in Producto.objects.exclude(imagen_principal="").exclude(imagen_principal__isnull=True).iterator():
        Imagen.objects.get_or_create(producto_id=p.pk, ruta_storage=p.imagen_principal.name,
            defaults={"nombre": "Imagen principal", "principal": True, "variantes": p.imagen_principal_variantes, "dimensiones": p.imagen_principal_dimensiones})


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0010_imagenproducto")]
    operations = [migrations.RunPython(conservar, migrations.RunPython.noop)]
