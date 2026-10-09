#!/usr/bin/env python3
"""Verifica la compatibilidad estática de F10 con una revisión fijada de homex-deploy."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _git(*args: str, cwd: Path) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def _exigir(texto: str, fragmento: str, origen: str) -> None:
    if fragmento not in texto:
        raise SystemExit(f"Falta {fragmento!r} en {origen}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("deploy", type=Path)
    parser.add_argument("--deploy-revision", required=True)
    args = parser.parse_args()
    deploy = args.deploy.resolve()

    revision_real = _git("rev-parse", args.deploy_revision, cwd=deploy)
    if revision_real != args.deploy_revision:
        raise SystemExit(
            "La revisión deploy no es exacta: "
            f"esperado={args.deploy_revision}, real={revision_real}"
        )

    def leer_revision(ruta: str) -> str:
        return _git("show", f"{revision_real}:{ruta}", cwd=deploy)

    manifest = leer_revision("releases/manifest.yaml")
    match = re.search(r"backend:\n\s+repository:.*\n\s+revision: ([0-9a-f]{40})", manifest)
    if not match:
        raise SystemExit("El manifiesto de deploy no fija una revisión backend")
    backend_base = match.group(1)
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", backend_base, "HEAD"],
        cwd=BACKEND_ROOT,
        check=True,
    )

    compose = leer_revision("compose.production.yml")
    for fragment in (
        "DJANGO_SETTINGS_MODULE: config.settings.production",
        "HOMEX_MEDIA_ROOT: /var/lib/homex/media",
        "audio_temporal:/var/lib/homex/audio-temporal",
        "source: ${HOMEX_MEDIA_HOST_PATH:?HOMEX_MEDIA_HOST_PATH is required}",
        "target: /var/lib/homex/media",
        "run_compose run --rm migrate",
    ):
        origen = (
            "compose.production.yml"
            if fragment != "run_compose run --rm migrate"
            else "scripts/deploy.sh"
        )
        texto = compose if origen == "compose.production.yml" else leer_revision(origen)
        _exigir(texto, fragment, origen)

    d05 = leer_revision("docs/implementacion/D05_RECOVERY.md")
    d06 = leer_revision("docs/implementacion/D06_OBSERVABILIDAD_RESILIENCIA.md")
    for fragment in ("restore", "PostgreSQL", "media", "audio temporal no se restauró"):
        _exigir(d05, fragment, "D05_RECOVERY.md")
    for fragment in ("outbox", "media read-only", "PostgreSQL", "Redis"):
        _exigir(d06, fragment, "D06_OBSERVABILIDAD_RESILIENCIA.md")

    urls = (BACKEND_ROOT / "config/urls.py").read_text(encoding="utf-8")
    _exigir(urls, 'path("api/v1/ready/", readiness', "config/urls.py")

    print(
        "f10-deploy-contract-ok "
        f"deploy={revision_real} backend_base={backend_base} d07_pending=true"
    )


if __name__ == "__main__":
    main()
