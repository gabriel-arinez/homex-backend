"""Métricas determinísticas: nunca confundir comparación de textos con exactitud."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from datetime import datetime

NORMALIZER = "nfc-casefold-punctuation-preserve-numeric-separators-v1"
CRITICAL = {"amount", "axis", "unit", "price", "currency", "price_mode", "quantity", "negation"}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).casefold()
    chars = []
    for i, char in enumerate(text):
        numeric_separator = char in ".,/:" and i + 1 < len(text) and text[i + 1].isdigit()
        signed_number = char in "+-−"
        chars.append(
            " "
            if unicodedata.category(char).startswith("P")
            and not numeric_separator
            and char not in "%‰"
            and not signed_number
            else char
        )
    return " ".join("".join(chars).split())


def align(reference, hypothesis) -> dict:
    """Levenshtein exacto; empates determinísticos: sustitución, borrado, inserción."""
    n, m = len(reference), len(hypothesis)
    costs = [list(range(m + 1))]
    for i in range(1, n + 1):
        row = [i]
        for j in range(1, m + 1):
            row.append(
                min(
                    costs[i - 1][j - 1] + (reference[i - 1] != hypothesis[j - 1]),
                    costs[i - 1][j] + 1,
                    row[j - 1] + 1,
                )
            )
        costs.append(row)
    operations = []
    i, j = n, m
    while i or j:
        if i and j and costs[i][j] == costs[i - 1][j - 1] + (reference[i - 1] != hypothesis[j - 1]):
            operations.append(
                {
                    "op": "H" if reference[i - 1] == hypothesis[j - 1] else "S",
                    "reference": reference[i - 1],
                    "hypothesis": hypothesis[j - 1],
                }
            )
            i, j = i - 1, j - 1
        elif i and costs[i][j] == costs[i - 1][j] + 1:
            operations.append({"op": "D", "reference": reference[i - 1], "hypothesis": None})
            i -= 1
        else:
            operations.append({"op": "I", "reference": None, "hypothesis": hypothesis[j - 1]})
            j -= 1
    operations.reverse()
    counts = Counter(o["op"] for o in operations)
    return {
        "reference_units": n,
        "hypothesis_units": m,
        "substitutions": counts["S"],
        "deletions": counts["D"],
        "insertions": counts["I"],
        "errors": costs[n][m],
        "rate": costs[n][m] / n if n else None,
        "empty_reference_insertions": counts["I"] if not n else 0,
        "alignment": operations,
    }


def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_references(
    records: list[dict], corpus: list[dict], *, provisional=False
) -> list[dict]:
    expected = {r["audio_id"]: r["audio_sha256"] for r in corpus}
    if len(expected) != len(corpus):
        raise ValueError("IDs duplicados en corpus")
    if len(records) != len(expected) or {r["audio_id"] for r in records} != set(expected):
        raise ValueError("IDs incompletos, duplicados o ajenos")
    for r in records:
        if r["audio_sha256"] != expected[r["audio_id"]]:
            raise ValueError("Referencia no corresponde al hash del audio")
        if r.get("verificacion_por_escucha") is not True:
            continue
        event = r.get("listening_evidence", {})
        audit = r.get("provenance_audit", {})
        text = r.get("texto_literal_verificado")
        if not isinstance(text, str):
            raise ValueError("Texto literal ausente")
        if not text.strip() and not r.get("notas_acusticas", {}).get("confirmed_silence"):
            raise ValueError("Referencia vacía requiere confirmación humana de silencio")
        if not (
            event.get("method") == "human_listening"
            and event.get("reviewer")
            and event.get("reviewed_at")
            and event.get("audio_sha256") == r["audio_sha256"]
            and event.get("audio_id") == r["audio_id"]
            and event.get("text_sha256") == text_digest(text)
            and (
                provisional
                or (
                    audit.get("audited_by")
                    and audit.get("audited_at")
                    and audit.get("status") == "AUDITADA"
                )
            )
        ):
            raise ValueError("Un booleano no acredita procedencia de escucha y auditoría")
        datetime.fromisoformat(event["reviewed_at"])
        if provisional:
            if (
                not isinstance(event.get("playback_ended_events"), int)
                or event["playback_ended_events"] < 1
            ):
                raise ValueError("Falta declaración de reproducción completa")
        else:
            datetime.fromisoformat(audit["audited_at"])
    return records


def score_reference(
    reference: dict, hypothesis: str, *, provisional=False, monetary_convention=None
) -> dict:
    """Requiere referencia validada y auditable; inaudibles no son texto adivinable."""
    validate_references([reference], [reference], provisional=provisional)
    if reference.get("verificacion_por_escucha") is not True:
        return {"status": "PENDIENTE_GOLD", "literal": None, "normalized": None}
    if reference.get("notas_acusticas", {}).get("uncertain_spans"):
        return {"status": "PENDIENTE_TRAMOS_INAUDIBLES", "literal": None, "normalized": None}
    text = reference["texto_literal_verificado"]
    from research.asr_opt.numeric import numeric_normalize

    numeric_ref = numeric_normalize(text, monetary_convention)
    numeric_hyp = numeric_normalize(hypothesis, monetary_convention)
    return {
        "numeric": {
            "wer": align(numeric_ref["text"].split(), numeric_hyp["text"].split()),
            "cer": align(list(numeric_ref["text"]), list(numeric_hyp["text"])),
        },
        "numeric_trace": {"reference": numeric_ref, "hypothesis": numeric_hyp},
        "status": "PROVISIONAL_REFERENCIA_DECLARADA" if provisional else "REFERENCIA_AUDITADA",
        "normalizer": NORMALIZER,
        "literal": {
            "wer": align(text.split(), hypothesis.split()),
            "cer": align(list(text), list(hypothesis)),
        },
        "normalized": {
            "wer": align(normalize(text).split(), normalize(hypothesis).split()),
            "cer": align(list(normalize(text)), list(normalize(hypothesis))),
        },
    }


def microaggregate(scores: list[dict], metric="wer", mode="literal") -> dict:
    valid = [s[mode][metric] for s in scores if s.get(mode) is not None]
    keys = ("reference_units", "substitutions", "deletions", "insertions", "errors")
    total = {k: sum(s[k] for s in valid) for k in keys}
    total.update(scored_audios=len(valid), pending_audios=len(scores) - len(valid))
    total["rate"] = total["errors"] / total["reference_units"] if total["reference_units"] else None
    return total


def monetary_relation(left: str, right: str, convention: str | None = None) -> str:
    """Clasifica formato, no interpreta cifras ambiguas sin convención explícita."""
    if left == right:
        return "IDENTICO"
    if re.fullmatch(r"\d{1,3}[.,]\d{3}", left) or re.fullmatch(r"\d{1,3}[.,]\d{3}", right):
        if convention not in {"es-BO", "en-US"}:
            return "AMBIGUEDAD_MONETARIA"
    if convention not in {"es-BO", "en-US"}:
        return "REQUIERE_CONTEXTO"
    from decimal import Decimal, InvalidOperation

    def parse(value):
        thousands, decimal = (".", ",") if convention == "es-BO" else (",", ".")
        if not re.fullmatch(r"[0-9.,]+", value):
            raise ValueError("Formato no numérico")
        integer, *fraction = value.split(decimal)
        if len(fraction) > 1 or (
            thousands in integer
            and not re.fullmatch(r"\d{1,3}(?:" + re.escape(thousands) + r"\d{3})+", integer)
        ):
            raise ValueError("Agrupación inválida")
        return Decimal(integer.replace(thousands, "") + ("." + fraction[0] if fraction else ""))

    try:
        return "FORMATO_EQUIVALENTE" if parse(left) == parse(right) else "CAMBIO_VALOR"
    except (ValueError, InvalidOperation):
        return "AMBIGUEDAD_MONETARIA"


def field_errors(gold: dict, hypothesis: dict) -> dict:
    """Campos gold anotados por humano: value/context/unit/axis/scope conservados."""
    rows = []
    for field in sorted(gold.keys() | hypothesis.keys()):
        expected, actual = gold.get(field), hypothesis.get(field)
        if field not in gold:
            rows.append({"field": field, "error": "NO_EVALUABLE", "severity": None})
            continue
        if expected == "INDETERMINADO" or (
            isinstance(expected, dict) and expected.get("status") == "INDETERMINADO"
        ):
            rows.append({"field": field, "error": "NO_EVALUABLE", "severity": None})
            continue
        if expected == actual:
            kind = "IGUAL"
        elif field not in hypothesis or actual is None:
            kind = "OMISION"
        elif field not in gold or expected is None:
            kind = "INVENCION"
        elif (
            isinstance(expected, dict)
            and isinstance(actual, dict)
            and (
                expected.get("value") == actual.get("value")
                and {k: v for k, v in expected.items() if k != "original_text"}
                == {k: v for k, v in actual.items() if k != "original_text"}
            )
        ):
            kind = "FORMATO"
        else:
            kind = "SUSTITUCION"
        rows.append(
            {
                "field": field,
                "error": kind,
                "severity": "CRITICA" if field.split(".")[-1] in CRITICAL else "ALTA",
                "gold": expected,
                "hypothesis": actual,
            }
        )
    evaluated = [r for r in rows if r["error"] != "NO_EVALUABLE"]
    return {
        "fields": rows,
        "denominator": len(evaluated),
        "errors": sum(r["error"] not in {"IGUAL", "FORMATO"} for r in evaluated),
    }
