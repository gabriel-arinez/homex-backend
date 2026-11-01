"""Adaptador offline de matriz de proyección a hechos tipados; sin Django/servicios.

La comparación exploratoria es condicionada al texto declarado. Nunca acredita gold.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

from research.asr_opt.evaluation import field_errors, text_digest
from research.asr_opt.numeric import canonical, numeric_normalize

UNKNOWN = "INDETERMINADO"
LABEL_KEYS = {
    "name",
    "product",
    "scope",
    "text",
    "nombre",
    "valor",
    "message",
    "mensaje",
    "restriction",
    "accessories",
    "accesorios",
    "materials",
    "colors",
    "detail",
}
NUMERIC_KEYS = {
    "value",
    "value_mm",
    "stated_amount",
    "line_total",
    "unit_price_input",
    "unit_price_reference",
    "quantity",
    "thickness_mm",
}


def typed_normalize(value, key=""):
    """Solo etiquetas explícitas admiten casefold; códigos/unidades/ejes permanecen."""
    if isinstance(value, dict):
        result = {}
        for k, v in value.items():
            if k == "text" and value.get("label") not in {
                "MATERIAL",
                "COLOR",
                "COMPONENTE",
                "CONJUNTO",
                "PRODUCTO",
            }:
                result[k] = v
            elif k == "valor" and value.get("nombre") not in {"Material", "Color"}:
                result[k] = v
            else:
                result[k] = typed_normalize(v, k)
        return result
    if isinstance(value, list):
        normalized = [typed_normalize(v, key) for v in value]
        if key in {"measures", "materials", "colors"}:
            return sorted(normalized, key=lambda v: repr(v))
        return normalized
    if isinstance(value, str) and key in LABEL_KEYS:
        return " ".join(
            token if token in {"m", "M", "cm", "mm", "BOB", "USD", "%", "‰"} else token.casefold()
            for token in unicodedata.normalize("NFC", value).split()
        )
    if isinstance(value, str) and key in NUMERIC_KEYS:
        try:
            return (
                canonical(value) if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", value) else value
            )
        except InvalidOperation:
            return value
    return value


def bind_projection(report, projection):
    """Une sin copiar manualmente; exige IDs, hashes y texto exacto del NLP."""
    predictions = report["records"]
    rows = projection["rows"]
    for group in (predictions, rows):
        if len(group) != len({r["audio_id"] for r in group}):
            raise ValueError("IDs duplicados")
    lookup = {r["audio_id"]: r for r in rows}
    if set(lookup) != {r["audio_id"] for r in predictions}:
        raise ValueError("IDs de matriz/predicción diferentes")
    result = []
    for row in predictions:
        p = lookup[row["audio_id"]]
        source = row.get("source_audio_sha256", row["audio_sha256"])
        if source != p["source_audio_sha256"] or p["nlp"]["text_original"] != row["transcription"]:
            raise ValueError("Matriz no corresponde a audio/texto")
        if text_digest(row["transcription"]) != row["text_sha256"]:
            raise ValueError("Hash de transcripción inválido")
        result.append(
            {
                **row,
                "commercial_fields": projection_facts(p),
                "commercial_fields_source": "projection-adapter-v1",
                "projection_row": p,
            }
        )
    return result


def text_facts(text, convention="es-BO"):
    """Extractor de diagnóstico con gramática limitada; no reemplaza NLP operativo."""
    n = numeric_normalize(text, convention)["text"]
    amount = re.search(r"(?<![\d.,])([+-]?\d+(?:\.\d+)?) bolivianos?\b", n)
    mode = (
        "negotiated_total" if "total negociado" in n else ("unit" if "unitario" in n else UNKNOWN)
    )
    dimensions = []
    for m in re.finditer(
        r"(?<![\d.,])(\d+(?:\.\d+)?) (metros?|centímetros?|milímetros?|m|cm|mm) "
        r"de (ancho|alto|largo|profundidad)\b",
        n,
    ):
        v, u, axis = m.groups()
        u = {
            "metro": "m",
            "metros": "m",
            "centímetro": "cm",
            "centímetros": "cm",
            "milímetro": "mm",
            "milímetros": "mm",
        }.get(u, u)
        dimensions.append({"value": canonical(v), "unit": u, "axis": axis})
    negatives = [
        {"scope": m.group(1), "restriction": "sin " + m.group(1)}
        for m in re.finditer(r"\bsin (chapa de seguridad|cajones|puertas|descuento)\b", n)
    ]
    return {
        "price.amount": canonical(amount[1]) if amount else UNKNOWN,
        "price.currency": "BOB" if amount else UNKNOWN,
        "price.mode": mode,
        "dimensions_explicit_grammar": dimensions,
        "negations_explicit_grammar": negatives,
        "normalized_text": n,
    }


def projection_facts(row):
    raw = row["nlp"]
    item = raw.get("item_proposal") or {}
    price = item.get("price") or {}
    modes = {"UNITARIO": "unit", "PRECIO_UNITARIO": "unit", "TOTAL_NEGOCIADO": "negotiated_total"}
    materials = [
        c["text"]
        for c in raw["candidates"]
        if c["label"] == "MATERIAL" and c["decision"] == "ACCEPTED"
    ]
    colors = [
        c["text"]
        for c in raw["candidates"]
        if c["label"] == "COLOR" and c["decision"] == "ACCEPTED"
    ]
    result = {
        "product": item.get("name"),
        "quantity": item.get("quantity"),
        "price.amount": price.get("stated_amount"),
        "price.currency": price.get("currency"),
        "price.mode": modes.get(price.get("mode"), price.get("mode")),
        "measures": [
            {
                "value": x["value"],
                "unit": x["unit"],
                "axis": x["axis"],
                "scope": x.get("component_ref") or "mueble",
            }
            for x in item.get("dimensions", [])
        ],
        "materials": materials,
        "colors": colors,
        "thicknesses": [
            {"value": x["value"], "unit": x["unit"], "scope": x.get("component_ref") or UNKNOWN}
            for x in item.get("thicknesses", [])
        ],
        "components": item.get("components", []),
        "accessories": item.get("accessories", []),
        # Un token no acredita representación de alcance en NLP/proyección.
        "negations": UNKNOWN,
        "proposal": raw.get("proposed_item_count"),
        "projected_type": ((row.get("projection") or {}).get("especificacion") or {}).get(
            "tipo_mueble"
        ),
    }
    return result


def draft_facts(draft):
    p = draft["price"]
    p = p if isinstance(p, dict) else {}
    return {
        "product": draft["item"],
        "quantity": draft["quantity"],
        "price.amount": p.get("value", UNKNOWN),
        "price.currency": p.get("currency", UNKNOWN),
        "price.mode": p.get("price_mode", UNKNOWN),
        "measures": draft["measures"],
        "materials": [x["name"] for x in draft["materials"]],
        "colors": draft["colors"],
        "thicknesses": [
            {"value": x["thickness_mm"], "unit": "mm", "scope": x["scope"]}
            for x in draft["materials"]
            if x["thickness_mm"] not in (None, UNKNOWN)
        ],
        "components": draft["components"],
        "accessories": UNKNOWN,
        "negations": draft["negations"],
        "proposal": 1,
        "projected_type": UNKNOWN,
    }


def dimension_comparisons(expected, actual):
    """Mismo eje/ámbito, unidades convertidas con Decimal; sin inferir ejes ausentes."""
    factors = {"m": Decimal(1000), "cm": Decimal(10), "mm": Decimal(1)}
    rows = []
    for e in expected:
        matches = [a for a in actual if a["axis"] == e["axis"]]
        if len(matches) > 1:
            rows.append({"expected": e, "status": "NO_EVALUABLE_EJE_DUPLICADO"})
            continue
        a = matches[0] if matches else None
        if a is not None and (a["unit"] not in factors or e["unit"] not in factors):
            rows.append(
                {
                    "expected": e,
                    "actual": a,
                    "equivalent_value_same_axis_scope": False,
                    "status": "NO_EVALUABLE_UNIDAD_NO_RESUELTA",
                }
            )
            continue
        same_scope = a is not None and e["scope"] == a["scope"]
        equivalent = (
            same_scope
            and Decimal(e["value"]) * factors[e["unit"]] == Decimal(a["value"]) * factors[a["unit"]]
        )
        rows.append(
            {
                "expected": e,
                "actual": a,
                "axis_present": a is not None,
                "same_scope": same_scope,
                "controlled_unit_conversion": a is not None and e["unit"] != a["unit"],
                "equivalent_value_same_axis_scope": equivalent,
                "status": "EQUIVALENTE"
                if equivalent
                else (
                    "NO_EVALUABLE_AMBITO" if a and not same_scope else "DISCREPANCIA_EXPLORATORIA"
                ),
            }
        )
    # Ejes inventados son diagnósticos separados y nunca aprobados por el adaptador.
    for a in actual:
        if a["axis"] not in {e["axis"] for e in expected}:
            rows.append({"expected": None, "actual": a, "status": "EJE_EXTRA_EN_SALIDA"})
    return rows


def compare_draft(draft, bound):
    expected = draft_facts(draft)
    actual = bound["commercial_fields"]
    rows = []
    spoken = text_facts(bound["transcription"])
    for field in expected:
        e, a = expected[field], actual.get(field)
        # El adaptador no puede certificar ámbitos/colecciones con ontologías diferentes.
        unavailable = e == UNKNOWN or a == UNKNOWN
        if field in {"components", "thicknesses"}:
            unavailable = True  # Ontologías/ámbitos no alineados: no fabricar denominador.
        strict = field_errors({field: e}, {field: a})["fields"][0]
        same = typed_normalize(e, field) == typed_normalize(a, field)
        if field in {"price.amount"} and a is not None and e != UNKNOWN:
            same = Decimal(e) == Decimal(a)
        status = (
            "NO_EVALUABLE"
            if unavailable
            else ("IGUAL_TIPADO" if same else "DISCREPANCIA_EXPLORATORIA")
        )
        origin = "AMBIGUO"
        if field.startswith("price.") and not unavailable and not same:
            origin = (
                "NLP"
                if spoken.get(field) == e
                or (
                    field == "price.amount"
                    and spoken.get(field) != UNKNOWN
                    and Decimal(spoken[field]) == Decimal(e)
                )
                else "ASR_O_GRAMATICA_DIAGNOSTICA"
            )
        if bound["commercial_fields"].get("proposal") == 0 and not same:
            origin = "AMBIGUO_ASR_NLP"
        if field == "projected_type":
            origin = "CATALOGO"
        rows.append(
            {
                "field": field,
                "expected": e,
                "actual": a,
                "literal_result": strict["error"],
                "status": status,
                "attribution": origin,
                "validity": "EXPLORATORIA_DERIVED_FROM_REVIEW_TEXT",
                "official_denominator": 0,
            }
        )
    from research.asr_opt.scopes import scoped_diagnostics

    scoped = (
        scoped_diagnostics(draft, bound["projection_row"]) if "projection_row" in bound else None
    )
    dimensions = dimension_comparisons(draft["measures"], actual["measures"])
    critical = [
        r
        for r in rows
        if r["field"] == "price.amount"
        and r["status"] == "DISCREPANCIA_EXPLORATORIA"
        and r["attribution"] == "NLP"
        and r["actual"] is not None
    ]
    return {
        "audio_id": bound["audio_id"],
        "fields": rows,
        "asr_diagnostics": spoken,
        "dimension_diagnostics": dimensions,
        "scoped_diagnostics": scoped,
        "negation_text_diagnostic": {
            "expected": draft["negations"],
            "recognized": spoken["negations_explicit_grammar"],
            "scope_grammar_limited": True,
            "pipeline_scope_status": "NO_EVALUABLE",
        },
        "promotion_gate": "BLOCK_CRITICAL_PIPELINE" if critical else "PENDING_HUMAN_VALIDATION",
        "official_denominator": 0,
        "exploratory_denominator": sum(r["status"] != "NO_EVALUABLE" for r in rows),
        "exploratory_discrepancies": sum(r["status"] == "DISCREPANCIA_EXPLORATORIA" for r in rows),
        "critical_pipeline_amounts": len(critical),
    }


def summarize(rows):
    counts = {}
    for row in rows:
        for f in row["fields"]:
            c = counts.setdefault(
                f["field"],
                {"evaluated": 0, "discrepancies": 0, "not_evaluable": 0, "official_denominator": 0},
            )
            c["not_evaluable"] += f["status"] == "NO_EVALUABLE"
            c["evaluated"] += f["status"] != "NO_EVALUABLE"
            c["discrepancies"] += f["status"] == "DISCREPANCIA_EXPLORATORIA"
    return {
        "fields": counts,
        "critical_pipeline_amounts": sum(r["critical_pipeline_amounts"] for r in rows),
        "official_denominator": 0,
        "validity": "EXPLORATORIA_NO_GOLD_COMERCIAL",
    }
