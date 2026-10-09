import os
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    return JsonResponse({"estado": "ok"})


def _postgresql_disponible() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            return cursor.fetchone() == (1,)
    except Exception:  # pragma: no cover - el driver concreta el error operativo
        return False


def _media_disponible() -> bool:
    try:
        if getattr(settings, "HOMEX_MEDIA_STORAGE", "filesystem") == "filesystem":
            root = Path(settings.MEDIA_ROOT)
            return root.is_dir() and os.access(root, os.R_OK | os.W_OK | os.X_OK)

        # HEAD sobre una key reservada: comprueba acceso al storage sin crear objetos.
        default_storage.exists(".homex-readiness")
        return True
    except Exception:
        return False


@require_GET
def readiness(request):
    dependencias = {
        "postgresql": "ok" if _postgresql_disponible() else "error",
        "media": "ok" if _media_disponible() else "error",
    }
    disponible = all(estado == "ok" for estado in dependencias.values())
    return JsonResponse(
        {"estado": "ok" if disponible else "no_disponible", "dependencias": dependencias},
        status=200 if disponible else 503,
    )
