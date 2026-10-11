from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("capturas", "0007_cierre_hitl_f083"),
    ]

    operations = [
        migrations.AddField(
            model_name="intentocaptura",
            name="ejecucion_token",
            field=models.UUIDField(blank=True, null=True),
        ),
    ]
