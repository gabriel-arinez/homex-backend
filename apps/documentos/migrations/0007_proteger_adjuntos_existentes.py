"""Move legacy customer images out of public storage without changing their IDs."""
from django.db import migrations, transaction


def proteger(apps, schema_editor):
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage
    from apps.media.services import keys_de_variantes
    from apps.media.storage import privado
    from uuid import uuid4

    Adjunto = apps.get_model("documentos", "ArchivoAdjunto")
    storage = privado()
    creados = []
    anteriores = []
    try:
        for imagen in Adjunto.objects.filter(privado=False).iterator():
            if not default_storage.exists(imagen.ruta_storage):
                # Preserve missing legacy references for repair; public proxy denies this prefix.
                continue
            claves = keys_de_variantes(imagen.ruta_storage)
            mapa = {}
            base = f"proformas/{uuid4()}"
            for key in claves:
                if not default_storage.exists(key):
                    continue
                with default_storage.open(key, "rb") as stream:
                    nueva = storage.save(f"{base}/{key.rsplit('/', 1)[-1]}", ContentFile(stream.read()))
                creados.append(nueva)
                anteriores.append(key)
                mapa[key] = nueva
            imagen.ruta_storage = mapa[claves[0]]
            imagen.variantes = {w: mapa[k] for w, k in zip(["320", "640", "1280"], claves[1:]) if k in mapa}
            imagen.privado = True
            imagen.save(update_fields=["ruta_storage", "variantes", "privado"])
        transaction.on_commit(lambda: [default_storage.delete(key) for key in anteriores])
    except Exception:
        for key in creados:
            storage.delete(key)
        raise


class Migration(migrations.Migration):
    dependencies = [("documentos", "0006_alter_archivoadjunto_options_and_more")]
    # No reverse: re-exposing customer references is unsafe. IDs and content are preserved.
    operations = [migrations.RunPython(proteger, migrations.RunPython.noop)]
