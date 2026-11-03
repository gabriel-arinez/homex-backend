from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [("proformas", "0011_ap3_idempotencia_guardado_integral")]

    operations = [
        # Primera operación: los registros existentes no tienen una hora fiable.
        migrations.AddField(
            model_name="proforma",
            name="creado_en",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        # Segunda operación: únicamente las nuevas proformas toman la hora real.
        migrations.AlterField(
            model_name="proforma",
            name="creado_en",
            field=models.DateTimeField(
                blank=True,
                default=django.utils.timezone.now,
                editable=False,
                null=True,
            ),
        ),
    ]
