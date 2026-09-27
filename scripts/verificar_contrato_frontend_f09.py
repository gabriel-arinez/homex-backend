"""Compara semánticamente OpenAPI y valida la referencia backend del frontend."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHA_COMPLETO = re.compile(r"[0-9a-f]{40}")


def ejecutar() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Uso: verificar_contrato_frontend_f09.py <directorio-frontend>")

    frontend = Path(sys.argv[1]).resolve()
    contrato_backend = yaml.safe_load((PROJECT_ROOT / "docs/openapi.yaml").read_text())
    contrato_frontend = yaml.safe_load((frontend / "contracts/backend-openapi.yaml").read_text())
    if contrato_backend != contrato_frontend:
        raise AssertionError("El snapshot OpenAPI consumido por Vue diverge del backend.")

    referencia = (frontend / "contracts/backend-ref.txt").read_text().strip()
    if SHA_COMPLETO.fullmatch(referencia) is None:
        raise AssertionError("backend-ref.txt no contiene un commit SHA-1 completo.")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", referencia, "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
    )
    print(f"f09-contract-consumer-ok backend_ref={referencia}")


if __name__ == "__main__":
    ejecutar()
