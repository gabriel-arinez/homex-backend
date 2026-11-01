"""Auditoría documental offline; no declara nueva escucha ni edita atestaciones."""

from __future__ import annotations

import wave
from datetime import datetime
from pathlib import Path

from research.asr_opt.evaluation import text_digest, validate_references
from research.asr_opt.runner import sha256


def audit_references(document, corpus):
    refs = document["records"]
    validate_references(refs, corpus, provisional=True)
    if {r["audio_id"] for r in refs} != {f"{i:02}" for i in range(1, 21)}:
        raise ValueError("Se requieren exactamente los 20 IDs")
    by_id = {r["audio_id"]: r for r in corpus}
    rows = []
    for ref in refs:
        source = by_id[ref["audio_id"]]
        p = Path(source["path"])
        if p.is_symlink() or sha256(p) != source["audio_sha256"]:
            raise ValueError("WAV original no corresponde")
        with wave.open(str(p)) as wav:
            if (wav.getnchannels(), wav.getframerate(), wav.getsampwidth(), wav.getcomptype()) != (
                1,
                16000,
                2,
                "NONE",
            ):
                raise ValueError("Formato WAV inesperado")
            duration = wav.getnframes() / wav.getframerate()
        event = ref["listening_evidence"]
        date = datetime.fromisoformat(event["reviewed_at"])
        if date.tzinfo is None or ref.get("public_release_authorized") is not False:
            raise ValueError("Timestamp sin zona o privacidad inconsistente")
        if ref.get("notas_acusticas", {}).get("uncertain_spans"):
            raise ValueError("Hay tramos dudosos; excluir del scoring completo")
        rows.append(
            {
                "audio_id": ref["audio_id"],
                "audio_sha256": sha256(p),
                "text_sha256": text_digest(ref["texto_literal_verificado"]),
                "duration_s": duration,
                "reviewer_declared": event["reviewer"],
                "reviewed_at_declared": event["reviewed_at"],
                "playback_ended_events_declared": event["playback_ended_events"],
                "provenance_status_original": ref["provenance_audit"]["status"],
                "documentary_status": "REFERENCIA_DECLARADA_VALIDADA_TECNICAMENTE",
                "independent_acoustic_audit": False,
            }
        )
    return {
        "records": rows,
        "valid": len(rows),
        "independent_acoustic_audited": 0,
        "reviewer_count": len({r["reviewer_declared"] for r in rows}),
        "declared_timestamp_count": len({r["reviewed_at_declared"] for r in rows}),
        "commercial_confirmed_fields": 0,
        "source_unchanged": True,
    }


def validate_drafts(document, references, review_sha256):
    if document["reference_json_sha256"] != review_sha256:
        raise ValueError("Borrador desvinculado del archivo de revisión")
    rows = document["records"]
    lookup = {r["audio_id"]: r for r in references}
    if len(rows) != len(lookup) or {r["audio_id"] for r in rows} != set(lookup):
        raise ValueError("IDs de borrador incompletos/duplicados")
    for row in rows:
        ref = lookup[row["audio_id"]]
        if row["source_audio_sha256"] != ref["audio_sha256"] or row[
            "source_text_sha256"
        ] != text_digest(ref["texto_literal_verificado"]):
            raise ValueError("Borrador no corresponde a fuente")
        if row.get("public_release_authorized") is not False:
            raise ValueError("Privacidad borrador inconsistente")
    return rows
