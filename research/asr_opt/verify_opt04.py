"""Standalone read-only dossier verification: no inference, network, DB or writes."""

import sys

sys.dont_write_bytecode = True
import hashlib
import json
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify(root):
    manifest = json.loads((root / "manifest_sha256.json").read_text())
    external = json.loads((root / "external_inputs_sha256.json").read_text())
    failures = []
    for kind, entries in [("files", manifest["files"]), ("externals", external["files"])]:
        for name, info in entries.items():
            path = Path(name)
            if kind == "files":
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("Unsafe relative path")
                path = root / path
            elif not path.is_absolute():
                raise ValueError("External path must be absolute")
            try:
                if (
                    path.is_symlink()
                    or not path.is_file()
                    or path.stat().st_size != info["bytes"]
                    or digest(path) != info["sha256"]
                ):
                    failures.append(name)
            except OSError:
                failures.append(name)
        print(("PASS" if not failures else "FAIL") + ": " + kind + " " + str(len(entries)))
    pair = json.loads((root / "04_COMPARACION_COMERCIAL_ANTES_DESPUES.json").read_text())
    assert pair["same_catalog"] and pair["same_60_transcriptions"] and len(pair["rows"]) == 60
    assert pair["official_denominator"] == pair["independent_acoustic_audited"] == 0
    assert sum(r["classification"] == "CORRECCION_DE_BUG" for r in pair["rows"]) == 2
    assert all(r["classification"] in ["CORRECCION_DE_BUG", "SIN_CAMBIO"] for r in pair["rows"])
    experiments = json.loads((root / "06_RESULTADOS_ASR_OPT_04.json").read_text())
    assert experiments["in_sample"] and experiments["official_denominator"] == 0
    assert len(experiments["experiments"]) == 12
    assert {e["model"] for e in experiments["experiments"]} == {"small", "medium", "large-v3-turbo"}
    assert all(e["status"] != "STARTING" for e in experiments["experiments"])
    models = manifest["model_identities"]
    profiles = manifest["profiles"]
    reports = manifest["inference_reports"]
    for filename in reports:
        data = json.loads((root / filename).read_text())
        request = data["request"]
        model = request["model_id"]
        profile = request["profile_id"]
        assert model in models and profile in profiles
        assert request["model_sha256"] == models[model]["files"]["model.bin"]["sha256"]
        assert data["verified_model_identity"] == models[model]
        assert data["transcribe_kwargs"] == {"language": "es", **profiles[profile]}
        assert data["effective_device"] == "cpu" and data["effective_compute_type"] in {
            "int8",
            "int8_float32",
        }
        assert data["versions"] == {
            "faster-whisper": "1.2.1",
            "ctranslate2": "4.8.2",
            "homex-nlp": "0.1.18",
        }
        if data["status"] == "PASS":
            assert len(data["records"]) == len(request["records"])
        expected = {r["audio_id"]: r["audio_sha256"] for r in request["records"]}
        assert len(expected) == len(request["records"])
        for row in data["records"]:
            assert row["audio_sha256"] == expected[row["audio_id"]]
            assert hashlib.sha256(row["transcription"].encode()).hexdigest() == row["text_sha256"]
            assert row["transcription"] == " ".join(
                s["text"].strip() for s in row["segments"] if s["text"].strip()
            )
    print(
        "PASS: paired60 and "
        + str(len(reports))
        + " experimental inference reports; versions/kwargs/identities/text hashes"
    )
    print(
        "PENDING: independent acoustic audit and human commercial confirmation; official denominator0"
    )
    return failures


if __name__ == "__main__":
    try:
        root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
        raise SystemExit(1 if verify(root) else 0)
    except (OSError, ValueError, KeyError, TypeError, AssertionError) as error:
        print("FAIL: " + str(error))
        raise SystemExit(1) from error
