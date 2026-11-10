"""Conservative source-clause coverage, never fuzzy/token-based summarization."""

import re


def clauses(value):
    # Do not split decimal measurements or semicolon-linked technical context.
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", value) if s.strip()]


def normalized(value):
    return " ".join(value.casefold().split()).rstrip(".!?")


def additional_source(source, structured, extra=()):
    """Only complete identical descriptive clauses can prove coverage.

    Scalar attribute values cannot prove a relationship in a source sentence.
    No stemming, word sets, numeric coercion, or cross-component merging occurs.
    Once unmatched context occurs, subsequent clauses remain verbatim, even
    when their standalone wording exists under another structured component.
    """
    covered = set()

    def visit(value, key=""):
        if isinstance(value, dict):
            for name, child in value.items():
                if name != "descripcion_original":
                    visit(child, name)
        elif isinstance(value, list):
            for child in value:
                visit(child, key)
        elif isinstance(value, str) and key in {
            "detalle",
            "descripcion",
            "observaciones",
            "advertencias",
            "cerraduras",
            "cerradura",
        }:
            covered.update(normalized(part) for part in clauses(value))

    visit(structured)
    for value in extra:
        if isinstance(value, str):
            covered.update(normalized(part) for part in clauses(value))
    retained = []
    uncertain_context = False
    for part in clauses(source or ""):
        if normalized(part) not in covered:
            # An unmatched heading/sentence can establish a different component
            # for subsequent identical wording. Without a proven scoped mapping,
            # retain the rest of that source context rather than detach its facts.
            uncertain_context = True
        if uncertain_context:
            retained.append(part)
    return retained
