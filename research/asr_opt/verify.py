"""Verificación offline de solo lectura: no inferencia, red, DB ni escrituras."""

from __future__ import annotations

import hashlib
import json
import sys
import wave
from pathlib import Path

sys.dont_write_bytecode = True


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def verify(root: Path) -> list[dict]:
    manifest = json.loads((root / "manifest_sha256.json").read_text())
    rows = []
    for category in ("files", "external_inputs"):
        entries = manifest[category]
        failures = []
        for filename, info in entries.items():
            path = Path(filename)
            if category == "files":
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("Ruta fuera de expediente")
                path = root / path
            try:
                if (
                    path.is_symlink()
                    or path.stat().st_size != info["bytes"]
                    or digest(path) != info["sha256"]
                ):
                    failures.append(filename)
            except OSError:
                failures.append(filename)
        rows.append(
            {
                "evidence": category,
                "status": "FALLÓ" if failures else "APROBADO",
                "count": len(entries),
                "failures": failures,
            }
        )
    corpus = json.loads((root / "privado/corpus.json").read_text())["records"]
    valid = len(corpus) == 20 and {r["audio_id"] for r in corpus} == {
        f"{i:02}" for i in range(1, 21)
    }
    for row in corpus:
        with wave.open(row["path"]) as audio:
            valid = valid and (
                audio.getnchannels(),
                audio.getframerate(),
                audio.getsampwidth(),
                audio.getcomptype(),
            ) == (1, 16000, 2, "NONE")
            valid = (
                valid and abs(audio.getnframes() / audio.getframerate() - row["duration_s"]) < 1e-9
            )
    rows.append(
        {"evidence": "20 WAV/IDs/formato/duracion", "status": "APROBADO" if valid else "FALLÓ"}
    )
    refs = json.loads((root / "privado/revision/references-pending.json").read_text())
    verified = sum(r.get("verificacion_por_escucha") is True for r in refs)
    rows.append(
        {
            "evidence": "gold humano auditado",
            "status": "PENDIENTE",
            "verified_attestations": verified,
            "note": "Hash/booleano no certifican escucha humana; requiere auditoría de exportación",
        }
    )
    for report in manifest.get("inference_reports", []):
        data = json.loads((root / report).read_text())
        versions = data.get("versions", {})
        valid = (
            versions.get("faster-whisper") == "1.2.1"
            and versions.get("ctranslate2") == "4.8.2"
            and versions.get("homex-nlp") == "0.1.18"
        )
        request = data.get("request", {})
        predictions = data.get("records", [])
        expected = {r["audio_id"]: r["audio_sha256"] for r in corpus}
        valid = valid and data.get("status") == "PASS"
        valid = valid and len(predictions) == len(request["records"])
        valid = valid and request["model_id"] in {"small", "medium", "large-v3-turbo"}
        valid = valid and request["model_sha256"] == manifest["model_weights"][request["model_id"]]
        for prediction in predictions:
            valid = valid and isinstance(prediction["transcription"], str)
            valid = valid and isinstance(prediction["segments"], list)
            valid = valid and prediction["inference_s"] >= 0
            valid = (
                valid
                and prediction.get("source_audio_sha256", prediction["audio_sha256"])
                == (expected[prediction["audio_id"]])
            )
        rows.append(
            {"evidence": "runtime/schema " + report, "status": "APROBADO" if valid else "FALLÓ"}
        )
    rows.append({"evidence": "micrófono real/precisión comparada", "status": "PENDIENTE"})
    return rows


if __name__ == "__main__":
    try:
        path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
        results = verify(path)
        for result in results:
            print(result["status"] + ": " + result["evidence"])
        raise SystemExit(1 if any(r["status"] == "FALLÓ" for r in results) else 0)
    except (OSError, ValueError, KeyError, TypeError, IndexError, EOFError, wave.Error) as error:
        print("FALLÓ: evidencia ausente, esquema inválido o no legible: " + str(error))
        raise SystemExit(1) from error
