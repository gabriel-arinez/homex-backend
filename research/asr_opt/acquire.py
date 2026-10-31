"""Descarga explícita de dos candidatos autorizados, siempre por revisión inmutable."""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

from research.asr_opt.identity import IDENTITIES, validate_origin, verify_model
from research.asr_opt.runner import memory, sha256

REPOS = {
    "medium": "Systran/faster-whisper-medium",
    "large-v3-turbo": "dropbox-dash/faster-whisper-large-v3-turbo",
}


def acquire(metadata: dict, model_id: str, destination: Path) -> dict:
    repo = REPOS[model_id]
    revision = metadata["sha"]
    validate_origin(model_id, metadata["id"], revision)
    from faster_whisper.utils import _MODELS

    aliases = {
        "medium": "Systran/faster-whisper-medium",
        "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
    }
    if _MODELS[model_id] != aliases[model_id]:
        raise ValueError("Alias instalado distinto: auditar antes de descargar")
    if "mit" not in str(metadata.get("cardData", {})).lower():
        raise ValueError("Licencia no verificada")
    trusted = IDENTITIES[model_id]["files"]
    supplied = {f["rfilename"]: f for f in metadata["siblings"]}
    for name, info in trusted.items():
        if name not in supplied or supplied[name]["size"] != info["bytes"]:
            raise ValueError("Metadata no coincide con manifiesto confiable")
    destination.resolve().relative_to(Path.home() / "Descargas")
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    files = [
        f
        for f in metadata["siblings"]
        if f["rfilename"]
        in {
            "README.md",
            "config.json",
            "model.bin",
            "tokenizer.json",
            "vocabulary.txt",
            "vocabulary.json",
            "preprocessor_config.json",
        }
    ]
    if not {"model.bin", "config.json", "tokenizer.json"}.issubset({f["rfilename"] for f in files}):
        raise ValueError("Archivos requeridos ausentes")
    manifest = {
        "model_id": model_id,
        "repo": repo,
        "revision": revision,
        "installed_alias_repo": aliases[model_id],
        "license": metadata.get("cardData", {}).get("license"),
        "preflight": memory(),
        "files": [],
    }
    for file in files:
        name = file["rfilename"]
        target = destination / name
        url = f"https://huggingface.co/{repo}/resolve/{revision}/{name}"
        with urllib.request.urlopen(url, timeout=90) as response, target.open("xb") as stream:
            while block := response.read(1024 * 1024):
                stream.write(block)
        target.chmod(0o600)
        digest = sha256(target)
        expected = file.get("lfs", {}).get("sha256")
        pinned = trusted.get(name, {}).get("sha256")
        if (
            target.stat().st_size != file["size"]
            or (expected and expected != digest)
            or (pinned and pinned != digest)
        ):
            raise ValueError("Tamaño/hash de descarga distinto: no usar candidato")
        manifest["files"].append(
            {"filename": name, "sha256": digest, "bytes": target.stat().st_size, "source": url}
        )
        (destination / "provenance.json").write_text(json.dumps(manifest, indent=2))
    verify_model(model_id, destination)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("model_id", choices=REPOS)
    parser.add_argument("metadata", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--download", action="store_true", required=True)
    args = parser.parse_args()
    print(
        json.dumps(acquire(json.loads(args.metadata.read_text()), args.model_id, args.destination))
    )
