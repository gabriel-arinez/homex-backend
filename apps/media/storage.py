from django.conf import settings
from django.core.files.storage import FileSystemStorage, storages


def privado():
    if "private" in settings.STORAGES:
        return storages["private"]
    return FileSystemStorage(location=settings.MEDIA_ROOT / ".private")
