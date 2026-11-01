"""Pinned wheel + installed bytes. Acoustic and commercial identities stay separate."""

from __future__ import annotations

import hashlib
import json
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from zipfile import ZipFile

REGISTRY = Path(__file__).with_name("nlp-identities.json")


def identity(selector):
    entries = json.loads(REGISTRY.read_text())
    if selector not in entries:
        raise ValueError("Identidad NLP desconocida; seleccione una entrada fijada")
    return {"id": selector, **{k: v for k, v in entries[selector].items() if k != "files"}}


def validate_metadata(metadata, selector):
    if metadata != identity(selector):
        raise ValueError("Identidad NLP incompleta o incompatible con el wheel fijado")


def verify_installed(selector, wheel):
    expected = identity(selector)
    wheel = Path(wheel)
    if not wheel.is_file():
        raise FileNotFoundError("Falta wheel NLP requerido: " + str(wheel))
    if hashlib.sha256(wheel.read_bytes()).hexdigest() != expected["wheel_sha256"]:
        raise ValueError("SHA256 de wheel NLP incompatible con identidad seleccionada")
    try:
        installed = distribution("homex-nlp")
    except PackageNotFoundError as exc:
        raise RuntimeError("Falta dependencia homex-nlp instalada") from exc
    if installed.version != expected["version"]:
        raise ValueError("Versión NLP instalada incompatible")
    files = json.loads(REGISTRY.read_text())[selector]["files"]
    with ZipFile(wheel) as archive:
        for name, digest in files.items():
            path = installed.locate_file(name)
            if (
                hashlib.sha256(archive.read(name)).hexdigest() != digest
                or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != digest
            ):
                raise ValueError("Bytes NLP instalados distintos del wheel: " + name)
    from homex_nlp.engine import RulesEngine

    if RulesEngine.rules_version != expected["rules"]:
        raise ValueError("Huella de reglas cargada incompatible")
    # Editable/shadow imports must not bypass installed-distribution verification.
    import homex_nlp.engine

    if (
        Path(homex_nlp.engine.__file__).resolve()
        != Path(installed.locate_file("homex_nlp/engine.py")).resolve()
    ):
        raise ValueError("Import NLP sombreado o editable; instale el wheel fijado")
    return expected


def historical_wheel():
    return Path(__file__).resolve().parents[2] / "vendor/homex_nlp-0.1.18-py3-none-any.whl"


def validate_matrix(matrix, selector, *, legacy=False):
    expected = identity(selector)
    if (
        matrix.get("nlp"),
        matrix.get("rules"),
        matrix.get("mode"),
        matrix.get("projection_version"),
        matrix.get("db_read_only"),
    ) != (expected["version"], expected["rules"], expected["mode"], "PRF04_2", True):
        raise ValueError("Matriz fuera del contrato NLP seleccionado")
    if legacy and selector == "historical-018" and "nlp_identity" not in matrix:
        return "LEGACY_METADATA_ONLY_NOT_WHEEL_ATTESTED"
    validate_metadata(matrix.get("nlp_identity"), selector)
    return "PINNED_IDENTITY"


def validate_acoustic_report(report, *, legacy=False):
    """No claim of installed-byte attestation for old metadata-only reports."""
    acoustic = report.get("nlp_identity")
    provenance = "PINNED_IDENTITY"
    if acoustic is None:
        if not legacy or report.get("versions", {}).get("homex-nlp") != "0.1.18":
            raise ValueError("Falta identidad NLP acústica; histórico requiere opt-in")
        acoustic = identity("historical-018")
        provenance = "LEGACY_METADATA_ONLY_NOT_WHEEL_ATTESTED"
    else:
        validate_metadata(acoustic, acoustic.get("id"))
    if report.get("versions") != {
        "faster-whisper": "1.2.1",
        "ctranslate2": "4.8.2",
        "homex-nlp": acoustic["version"],
    }:
        raise ValueError("Runtime acústico distinto de identidad declarada")
    return acoustic, provenance
