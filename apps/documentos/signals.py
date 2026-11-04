from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.catalogo.models import ImagenProducto
from apps.documentos.models import ArchivoAdjunto
from apps.media.services import keys_de_variantes
from apps.media.storage import privado


@receiver(post_delete, sender=ImagenProducto)
@receiver(post_delete, sender=ArchivoAdjunto)
def limpiar_imagen(sender, instance, **kwargs):
    storage = privado() if getattr(instance, "privado", False) else default_storage
    keys = [instance.ruta_storage, *instance.variantes.values()]
    if sender is ArchivoAdjunto and not instance.variantes:
        keys = keys_de_variantes(instance.ruta_storage)

    def borrar():
        # Legacy catalogue cover may also be referenced by a migrated gallery row.
        for key in keys:
            storage.delete(key)

    transaction.on_commit(borrar)
