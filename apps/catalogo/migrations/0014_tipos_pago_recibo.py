from django.db import migrations


def agregar_tipos_pago(apps, schema_editor):
    ConceptoCatalogo = apps.get_model("catalogo", "ConceptoCatalogo")
    ValorCatalogo = apps.get_model("catalogo", "ValorCatalogo")

    concepto = ConceptoCatalogo.objects.filter(codigo="TIPO_PAGO").first()
    if not concepto:
        return

    nuevos = [
        ("QR", "QR"),
        ("DEPOSITO", "Depósito"),
        ("TARJETA", "Tarjeta"),
    ]
    for codigo, nombre in nuevos:
        ValorCatalogo.objects.get_or_create(
            concepto=concepto,
            codigo=codigo,
            defaults={"nombre": nombre, "activo": True},
        )


def revertir_tipos_pago(apps, schema_editor):
    ConceptoCatalogo = apps.get_model("catalogo", "ConceptoCatalogo")
    ValorCatalogo = apps.get_model("catalogo", "ValorCatalogo")
    Recibo = apps.get_model("recibos", "Recibo")

    concepto = ConceptoCatalogo.objects.filter(codigo="TIPO_PAGO").first()
    if not concepto:
        return

    for codigo in ("QR", "DEPOSITO", "TARJETA"):
        valor = ValorCatalogo.objects.filter(concepto=concepto, codigo=codigo).first()
        if valor and not Recibo.objects.filter(tipo_pago_id=valor.id).exists():
            valor.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalogo", "0013_producto_stock_minimo_and_more"),
        ("recibos", "0004_recibo_clave_idempotencia"),
    ]

    operations = [
        migrations.RunPython(agregar_tipos_pago, revertir_tipos_pago),
    ]
