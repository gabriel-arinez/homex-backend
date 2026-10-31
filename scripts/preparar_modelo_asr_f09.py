"""Descarga explícita del modelo ASR del gate F09; el runtime no descarga modelos."""

from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path

from huggingface_hub import snapshot_download


def ejecutar() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("destino", type=Path)
    parser.add_argument("--small-research", action="store_true")
    args = parser.parse_args()
    destino = args.destino.resolve()
    if args.small_research:
        # ASR-OPT solo autoriza Small/Medium/Turbo. Es un fixture de CI, no runtime.
        snapshot_download(
            repo_id="Systran/faster-whisper-small",
            revision="536b0662742c02347bc0e980a01041f333bce120",
            local_dir=destino,
        )
        expected = "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671"
        if sha256((destino / "model.bin").read_bytes()).hexdigest() != expected:
            raise SystemExit("El fixture Small no corresponde al hash auditado")
    else:
        snapshot_download(repo_id="Systran/faster-whisper-base", local_dir=destino)
    if not (destino / "model.bin").is_file():
        raise SystemExit("El modelo ASR descargado no contiene model.bin")
    print(f"f09-asr-model-ok path={destino}")


if __name__ == "__main__":
    ejecutar()
