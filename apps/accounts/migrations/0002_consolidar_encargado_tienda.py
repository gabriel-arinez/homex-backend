from django.db import migrations


def consolidar_rol_encargado_tienda(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("accounts", "User")

    grupo_encargado, _ = Group.objects.get_or_create(name="ENCARGADO_TIENDA")
    Group.objects.get_or_create(name="JEFE_TALLER")

    grupo_vendedor = Group.objects.filter(name="VENDEDOR").first()
    if grupo_vendedor is None:
        return

    through = User.groups.through
    usuarios_vendedor = list(
        through.objects.filter(group_id=grupo_vendedor.pk).values_list("user_id", flat=True)
    )
    if not usuarios_vendedor:
        return

    existentes = set(
        through.objects.filter(
            group_id=grupo_encargado.pk,
            user_id__in=usuarios_vendedor,
        ).values_list("user_id", flat=True)
    )
    nuevos = [
        through(user_id=user_id, group_id=grupo_encargado.pk)
        for user_id in usuarios_vendedor
        if user_id not in existentes
    ]
    if nuevos:
        through.objects.bulk_create(nuevos)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            consolidar_rol_encargado_tienda,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
