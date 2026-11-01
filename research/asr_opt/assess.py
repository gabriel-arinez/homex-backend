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


def assess(
    corpus_path,
    references_path,
    drafts_path,
    report_path,
    matrix_path,
    *,
    nlp_identity="historical-018",
    legacy_historical=False,
):
    def load(p):
        return json.loads(Path(p).read_text())

    corpus = load(corpus_path)["records"]
    refs = load(references_path)
    audit = audit_references(refs, corpus)
    drafts = validate_drafts(load(drafts_path), refs["records"], sha256(Path(references_path)))
    report = load(report_path)
    matrix = load(matrix_path)
    from research.asr_opt.nlp_identity import identity, validate_acoustic_report, validate_matrix

    provenance = validate_matrix(matrix, nlp_identity, legacy=legacy_historical)
    acoustic, acoustic_provenance = validate_acoustic_report(report, legacy=legacy_historical)
    if (
        report.get("status") != "PASS"
        or report.get("call") != "model.transcribe(path, language='es')"
    ):
        raise ValueError("Reporte incompleto o llamada distinta")
    matches = [p for p in matrix["reports"] if Path(p["source"]).name == Path(report_path).name]
    if len(matches) != 1:
        raise ValueError("Fuente de proyección ausente/ambigua")
    bound = bind_projection(report, matches[0])
    lookup = {r["audio_id"]: r for r in drafts}
    commercial = [compare_draft(lookup[r["audio_id"]], r) for r in bound]
    return {
        "validity": "PROVISIONAL_CONDICIONADA_AL_TEXTO_DECLARADO",
        "audit": audit,
        "commercial_nlp_identity": identity(nlp_identity),
        "commercial_identity_provenance": provenance,
        "acoustic_runtime_nlp_identity": acoustic,
        "acoustic_identity_provenance": acoustic_provenance,
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
    parser.add_argument("--nlp-identity", default="historical-018")
    parser.add_argument("--legacy-historical", action="store_true")
    a = parser.parse_args()
    os.umask(0o077)
    if a.output.exists():
        raise FileExistsError("No sobrescribir resultados")
    result = assess(
        a.corpus,
        a.references,
        a.drafts,
        a.report,
        a.matrix,
        nlp_identity=a.nlp_identity,
        legacy_historical=a.legacy_historical,
    )
    with a.output.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
