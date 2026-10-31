"""Diagnósticos parciales por evidencia explícita; no resuelve ámbitos por parecido."""

from __future__ import annotations

from decimal import Decimal


def scoped_diagnostics(draft, row):
    raw = row["nlp"]
    item = raw.get("item_proposal") or {}
    components = item.get("components", [])
    names = {c["component_id"]: c["name"].casefold() for c in components}
    candidates = raw["candidates"]
    facts = {"components": [], "thicknesses": [], "materials": [], "negations": []}
    for expected in draft["components"]:
        matches = [c for c in components if c["name"].casefold() == expected["name"].casefold()]
        found = matches[0] if len(matches) == 1 else None
        quantities = [
            c["normalized_value"]
            for c in candidates
            if found
            and c["label"] == "CANTIDAD_INTERNA"
            and c.get("component_ref") == found["component_id"]
            and c["decision"] == "ACCEPTED"
        ]
        facts["components"].append(
            {
                "expected": expected,
                "name_matched": bool(found),
                "internal_quantity_candidates": quantities,
                "quantity_equal": len(quantities) == 1 and quantities[0] == expected["quantity"],
                "parent_scope_status": "NO_EVALUABLE_RELACION_NO_REPRESENTADA",
                "status": "NOMBRE_OBSERVADO" if found else "SIN_CORRESPONDENCIA_UNIVOCA",
            }
        )
    for expected in draft["materials"]:
        scope = expected["scope"].casefold()
        material_matches = [
            c
            for c in candidates
            if c["label"] == "MATERIAL"
            and c.get("text", "").casefold() == expected["name"].casefold()
            and names.get(c.get("component_ref")) == scope
            and c["decision"] == "ACCEPTED"
        ]
        facts["materials"].append(
            {
                "expected": expected,
                "same_name_scope_observed": bool(material_matches),
                "status": "OBSERVADO" if material_matches else "NO_EVALUABLE_AMBITO_NO_RESUELTO",
            }
        )
        if expected["thickness_mm"] not in (None, "INDETERMINADO"):
            thicknesses = [
                t for t in item.get("thicknesses", []) if names.get(t.get("component_ref")) == scope
            ]
            resolved = len(thicknesses) == 1 and thicknesses[0].get("unit") == "mm"
            same = resolved and Decimal(thicknesses[0]["value"]) == Decimal(
                expected["thickness_mm"]
            )
            facts["thicknesses"].append(
                {
                    "expected_scope": scope,
                    "expected_mm": expected["thickness_mm"],
                    "actual": thicknesses,
                    "status": ("IGUAL_VALOR_AMBITO" if same else "DISCREPANCIA_EXPLORATORIA")
                    if resolved
                    else "NO_EVALUABLE_AMBITO_NO_RESUELTO",
                }
            )
    for expected in draft["negations"]:
        rejected = [
            c
            for c in candidates
            if c.get("text", "").casefold() == expected["scope"].casefold()
            and c["decision"] == "REJECTED"
            and "excluid" in (c.get("reason") or "").casefold()
        ]
        facts["negations"].append(
            {
                "expected": expected,
                "explicit_exclusion_evidence": rejected,
                "status": "EXCLUSION_NLP_OBSERVADA"
                if rejected
                else "NO_EVALUABLE_EXCLUSION_NO_REPRESENTADA",
                "projection_scope_status": "PENDIENTE_VALIDACION_RELACION",
            }
        )
    return facts
