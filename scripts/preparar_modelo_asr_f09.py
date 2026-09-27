"""Descarga explícita del modelo ASR del gate F09; el runtime no descarga modelos."""

from __future__ import annotations

import sys
from pathlib import Path

from huggingface_hub import snapshot_download


def ejecutar() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Uso: preparar_modelo_asr_f09.py <directorio-destino>")
    destino = Path(sys.argv[1]).resolve()
    snapshot_download(repo_id="Systran/faster-whisper-base", local_dir=destino)
    if not (destino / "model.bin").is_file():
        raise SystemExit("El modelo ASR descargado no contiene model.bin")
    print(f"f09-asr-model-ok path={destino}")


if __name__ == "__main__":
    ejecutar()
