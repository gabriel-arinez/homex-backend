#!/usr/bin/env python3
"""Smoke no comercial del runtime productivo F10."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.core.files.base import ContentFile  # noqa: E402
from django.core.files.storage import default_storage  # noqa: E402
from django.db import connection  # noqa: E402
from django.db.migrations.executor import MigrationExecutor  # noqa: E402
from django.test import Client  # noqa: E402


def main() -> None:
    plan = MigrationExecutor(connection).migration_plan(
        MigrationExecutor(connection).loader.graph.leaf_nodes()
    )
    if plan:
        raise SystemExit(f"Hay migraciones pendientes: {plan}")

    media = Path(settings.MEDIA_ROOT).resolve(strict=False)
    audio = Path(settings.HOMEX_AUDIO_TEMP_ROOT).resolve(strict=False)
    if media == audio or media in audio.parents or audio in media.parents:
        raise SystemExit("Media persistente y audio temporal se solapan")

    key = default_storage.save("productos/.f10-runtime-probe", ContentFile(b"f10"))
    try:
        if not key.startswith("productos/") or not default_storage.exists(key):
            raise SystemExit("El storage no preserva el prefijo productos/")
    finally:
        default_storage.delete(key)

    respuesta = Client().get("/api/v1/ready/")
    if respuesta.status_code != 200:
        raise SystemExit(f"Readiness falló: {respuesta.status_code} {respuesta.content!r}")

    print("f10-runtime-ok migrations=ok postgresql=ok media=ok audio_separado=true")


if __name__ == "__main__":
    main()
