"""CLI de métricas: ausencia de gold produce PENDIENTE y tasas null."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.asr_opt.evaluation import (
    field_errors,
    microaggregate,
    score_reference,
    validate_references,
)


def evaluate(corpus, references, hypotheses, *, provisional=False, monetary_convention=None):
    validate_references(references, corpus, provisional=provisional)
    expected = {r["audio_id"]: r["audio_sha256"] for r in corpus}
    if len(hypotheses) != len(corpus) or {r["audio_id"] for r in hypotheses} != set(expected):
        raise ValueError("Predicciones incompletas o IDs duplicados")
    refs = {r["audio_id"]: r for r in references}
    scores = []
    for row in hypotheses:
        source = row.get("source_audio_sha256", row["audio_sha256"])
        if source != expected[row["audio_id"]]:
            raise ValueError("Predicción corresponde a otro audio")
        scores.append(
            {
                "audio_id": row["audio_id"],
                **score_reference(
                    refs[row["audio_id"]],
                    row["transcription"],
                    provisional=provisional,
                    monetary_convention=monetary_convention,
                ),
            }
        )
    commercial = []
    for row in hypotheses:
        ref = refs[row["audio_id"]]
        ready = next(s for s in scores if s["audio_id"] == row["audio_id"])["literal"] is not None
        if (
            ready
            and not provisional
            and "commercial_fields" in row
            and ref.get("campos_comerciales_gold")
        ):
            commercial.append(
                {
                    "audio_id": row["audio_id"],
                    "source": row.get("commercial_fields_source", "MANUAL_TYPED_FIELDS"),
                    **field_errors(ref["campos_comerciales_gold"], row["commercial_fields"]),
                }
            )
        else:
            commercial.append(
                {
                    "audio_id": row["audio_id"],
                    "status": "PENDIENTE_CAMPOS_GOLD",
                    "errors": None,
                    "denominator": 0,
                }
            )
    return {
        "scores": scores,
        "commercial": commercial,
        "micro": {
            mode: {metric: microaggregate(scores, metric, mode) for metric in ("wer", "cer")}
            for mode in ("literal", "normalized", "numeric")
        },
        "status": "PENDIENTE_GOLD"
        if any(s["literal"] is None for s in scores)
        else ("PROVISIONAL_REFERENCIAS_DECLARADAS" if provisional else "REFERENCIAS_AUDITADAS"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", type=Path)
    parser.add_argument("references", type=Path)
    parser.add_argument("predictions", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--provisional-declared",
        action="store_true",
        help="No acredita auditoría acústica ni modifica referencias",
    )
    parser.add_argument("--monetary-convention", choices=("es-BO", "en-US"))
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("No sobrescribir evaluaciones")
    refs = json.loads(args.references.read_text())
    if isinstance(refs, dict):
        refs = refs["records"]
    result = evaluate(
        json.loads(args.corpus.read_text())["records"],
        refs,
        json.loads(args.predictions.read_text())["records"],
        provisional=args.provisional_declared,
        monetary_convention=args.monetary_convention,
    )
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
