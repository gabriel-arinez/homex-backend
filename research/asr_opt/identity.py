"""Identidades fijadas desde manifiestos históricos; comprobación offline completa."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

IDENTITIES = json.loads(Path(__file__).with_name("model-identities.json").read_text())
CRITICAL_FILES = {"model.bin", "config.json", "tokenizer.json"}


def validate_origin(model_id, repo, revision):
    expected = IDENTITIES[model_id]
    if repo != expected["repo"] or revision != expected["revision"]:
        raise ValueError("Repo/revisión fuera de la identidad preaprobada")


def verify_model(model_id, directory):
    expected = IDENTITIES[model_id]
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Ruta de modelo inválida")
    if not CRITICAL_FILES.issubset(expected["files"]):
        raise ValueError("Manifiesto confiable incompleto")
    # Cualquier auxiliar no fijado puede alterar carga/tokenización: fail closed.
    for name in (
        "config.json",
        "tokenizer.json",
        "vocabulary.txt",
        "vocabulary.json",
        "preprocessor_config.json",
        "model.bin",
    ):
        p = directory / name
        if p.exists() and name not in expected["files"]:
            raise ValueError("Auxiliar no auditado: " + name)
    for name, info in expected["files"].items():
        p = directory / name
        if p.is_symlink() or not p.is_file() or p.stat().st_size != info["bytes"]:
            raise ValueError("Archivo de modelo ausente/tamaño distinto: " + name)
        h = hashlib.sha256()
        with p.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(block)
        if h.hexdigest() != info["sha256"]:
            raise ValueError("Hash auxiliar/peso distinto: " + name)
    return expected
