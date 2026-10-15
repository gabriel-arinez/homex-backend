from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("proformas", "0010_ap6021_validacion_y_rollback_seguro")]

    operations = [
        migrations.AddField(
            model_name="proforma",
            name="clave_idempotencia",
            field=models.UUIDField(blank=True, editable=False, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="proforma",
            name="idempotencia_hash",
            field=models.CharField(blank=True, editable=False, max_length=64, null=True),
        ),
        migrations.AddConstraint(
            model_name="proforma",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(clave_idempotencia__isnull=True, idempotencia_hash__isnull=True)
                    | models.Q(clave_idempotencia__isnull=False, idempotencia_hash__isnull=False)
                ),
                name="ck_proforma_idempotencia_completa",
            ),
        ),
    ]
