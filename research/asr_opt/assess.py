"""CLI offline: referencia declarada, informe runner y proyección -> evaluación.

No carga modelos, servicios ni NLP. Salida siempre privada y provisional.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from research.asr_opt.commercial import bind_projection, compare_draft, summarize
from research.asr_opt.evaluate import evaluate
from research.asr_opt.review_audit import audit_references, validate_drafts
from research.asr_opt.runner import sha256


def assess(corpus_path, references_path, drafts_path, report_path, matrix_path):
    def load(p):
        return json.loads(Path(p).read_text())

    corpus = load(corpus_path)["records"]
    refs = load(references_path)
    audit = audit_references(refs, corpus)
    drafts = validate_drafts(load(drafts_path), refs["records"], sha256(Path(references_path)))
    report = load(report_path)
    matrix = load(matrix_path)
    if (
        matrix.get("nlp"),
        matrix.get("rules"),
        matrix.get("mode"),
        matrix.get("projection_version"),
        matrix.get("db_read_only"),
    ) != ("0.1.18", "prf04-rules-final", "RULES_ONLY", "PRF04_2", True):
        raise ValueError("Matriz fuera del contrato congelado")
    if (
        report.get("status") != "PASS"
        or report.get("call") != "model.transcribe(path, language='es')"
    ):
        raise ValueError("Reporte incompleto o llamada distinta")
    if report.get("versions") != {
        "faster-whisper": "1.2.1",
        "ctranslate2": "4.8.2",
        "homex-nlp": "0.1.18",
    }:
        raise ValueError("Runtime distinto del contrato congelado")
    matches = [p for p in matrix["reports"] if Path(p["source"]).name == Path(report_path).name]
    if len(matches) != 1:
        raise ValueError("Fuente de proyección ausente/ambigua")
    bound = bind_projection(report, matches[0])
    lookup = {r["audio_id"]: r for r in drafts}
    commercial = [compare_draft(lookup[r["audio_id"]], r) for r in bound]
    return {
        "validity": "PROVISIONAL_CONDICIONADA_AL_TEXTO_DECLARADO",
        "audit": audit,
        "text": evaluate(
            corpus,
            refs["records"],
            report["records"],
            provisional=True,
            monetary_convention="es-BO",
        ),
        "commercial": commercial,
        "commercial_summary": summarize(commercial),
        "input_sha256": {
            str(p): sha256(Path(p))
            for p in [corpus_path, references_path, drafts_path, report_path, matrix_path]
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("corpus", "references", "drafts", "report", "matrix", "output"):
        parser.add_argument(name, type=Path)
    a = parser.parse_args()
    os.umask(0o077)
    if a.output.exists():
        raise FileExistsError("No sobrescribir resultados")
    result = assess(a.corpus, a.references, a.drafts, a.report, a.matrix)
    with a.output.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
