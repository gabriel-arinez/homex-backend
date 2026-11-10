"""Conservative source-clause coverage, never fuzzy/token-based summarization."""

import re
import unicodedata
from decimal import Decimal, InvalidOperation


def clauses(value):
    # Do not split decimal measurements or semicolon-linked technical context.
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", value) if s.strip()]


def normalized(value):
    return " ".join(value.casefold().split()).rstrip(".!?")


def additional_source(source, structured, extra=(), *, product_name=None):
    """Retain clauses unless exact descriptions or scoped capture grammar prove them.

    Scalar values alone cannot prove a source relationship. Explicit named
    dimensions and component thicknesses also require the same explicit unit.
    No stemming, word sets, unit inference or cross-component merging occurs.
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
    evidence = CaptureEvidence(structured, product_name)
    retained = []
    uncertain_context = False
    for part in clauses(source or ""):
        technical = evidence.without_commercial_suffix(part)
        if not technical:
            continue
        if not uncertain_context and evidence.covers(technical):
            continue
        part = technical
        if normalized(part) not in covered:
            # An unmatched heading/sentence can establish a different component
            # for subsequent identical wording. Without a proven scoped mapping,
            # retain the rest of that source context rather than detach its facts.
            uncertain_context = True
        if uncertain_context:
            retained.append(part)
    return retained


UNIT_NAMES = {
    "metro": "m",
    "metros": "m",
    "m": "m",
    "milímetro": "mm",
    "milímetros": "mm",
    "mm": "mm",
    "centímetro": "cm",
    "centímetros": "cm",
    "cm": "cm",
}
MEASURE = r"(?P<value>\d+(?:[.,]\d+)?)\s+(?P<unit>metros?|milímetros?|centímetros?|mm|cm|m)"


def folded(value):
    return "".join(
        c
        for c in unicodedata.normalize("NFD", normalized(str(value)))
        if unicodedata.category(c) != "Mn"
    )


def measurement(value):
    if isinstance(value, dict):
        number, unit = value.get("valor"), value.get("unidad")
    elif isinstance(value, str):
        match = re.fullmatch(MEASURE, normalized(value))
        if not match:
            return None
        number, unit = match.group("value", "unit")
    else:
        return None
    try:
        number = Decimal(str(number).replace(",", "."))
    except InvalidOperation:
        return None
    # Unitless measurements never prove coverage of a unit-bearing source.
    unit = UNIT_NAMES.get(normalized(str(unit)))
    return (number, unit) if number.is_finite() and unit else None


class CaptureEvidence:
    """Small full-match grammar: every relation must match its own structured node.

    Unsupported prose remains verbatim. This is not a general natural-language
    parser: no stemming, token overlap, inferred units or cross-node fact unions.
    """

    def __init__(self, data, product_name):
        self.data = data
        self.name = folded(product_name) if product_name else None

    @staticmethod
    def without_commercial_suffix(part):
        # Only explicit price/quotation narration is stale commercial input.
        # Keep every technical prefix exactly as captured, including punctuation.
        price = re.search(r"(?:^|,\s*)precio unitario\b", part, re.IGNORECASE)
        if price and re.fullmatch(
            r"precio unitario\s*,?\s*[\d.,]+\s+bolivianos"
            r"(?:,\s*(?:se\s*cotiza|secotiza) una sola mesa)?[.]?",
            part[price.start() :].lstrip(", "),
            re.IGNORECASE,
        ):
            return part[: price.start()].rstrip(", ")
        return part

    def dimensions(self, part):
        if not self.name:
            return False
        prefix = re.match(
            r"(?:necesito un(?:a)? )?(.+?), (?:una unidad de |de )", part, re.IGNORECASE
        )
        if not prefix or folded(prefix.group(1)) != self.name:
            return False
        remaining = part[prefix.end() :].rstrip(".")
        general = self.data.get("caracteristicas_generales")
        dimensions = general.get("dimensiones", {}) if isinstance(general, dict) else {}
        if not isinstance(dimensions, dict):
            return False
        pattern = MEASURE + r" de (?P<axis>largo|ancho|alto|profundidad)"
        pieces = re.split(r",\s*| y | por ", remaining)
        for piece in pieces:
            match = re.fullmatch(pattern, piece, re.IGNORECASE)
            if not match:
                return False
            captured = measurement({"valor": match.group("value"), "unidad": match.group("unit")})
            if not captured or captured != measurement(dimensions.get(match.group("axis").lower())):
                return False
        return bool(pieces)

    def component(self, part):
        # A component's material and thickness are matched within that component.
        match = re.fullmatch(
            r"(?P<name>.+?) de (?:(?P<material>.+?) de )?" + MEASURE, normalized(part)
        )
        if not match:
            return False
        components = self.data.get("componentes", [])
        for component in components if isinstance(components, list) else []:
            if not isinstance(component, dict) or folded(component.get("nombre", "")) != folded(
                match.group("name")
            ):
                continue
            if match.group("material") and folded(component.get("material", "")) != folded(
                match.group("material")
            ):
                continue
            captured = measurement({"valor": match.group("value"), "unidad": match.group("unit")})
            if captured and captured == measurement(component.get("espesor")):
                return True
        return False

    def covers(self, part):
        if self.dimensions(part):
            return True
        accessories = self.data.get("accesorios", [])
        if not isinstance(accessories, list):
            accessories = []
        fragments = [value.strip() for value in part.rstrip(".").split(",")]
        return bool(fragments) and all(
            self.component(fragment)
            or any(
                isinstance(accessory, str) and normalized(accessory) == normalized(fragment)
                for accessory in accessories
            )
            for fragment in fragments
        )
