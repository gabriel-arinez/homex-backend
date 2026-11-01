"""Conservative review gate for bound facts; never infers acoustic correctness."""

import json
from collections import defaultdict

LABELS = {
    "MATERIAL",
    "COLOR",
    "CANTIDAD_INTERNA",
    "ESPESOR",
    "ANCHO",
    "ALTO",
    "LARGO",
    "PROFUNDIDAD",
}


def scope_bindings(row):
    raw = row["nlp"]
    item = raw.get("item_proposal") or {}
    names = {c["component_id"]: c["name"].casefold() for c in item.get("components", [])}
    result = defaultdict(list)
    for c in raw["candidates"]:
        if c["label"] not in LABELS:
            continue
        value = c.get("normalized_value")
        if value is None:
            value = c["text"].casefold()
        key = (c["label"], json.dumps(value, ensure_ascii=False, sort_keys=True))
        ref = c.get("component_ref")
        scope = names.get(ref, "UNRESOLVED_COMPONENT") if ref else None
        result[key].append((scope, c["decision"]))
    return {key: sorted(value, key=repr) for key, value in result.items()}


def scope_changes(before, after):
    left, right = scope_bindings(before), scope_bindings(after)
    return [
        {
            "label": key[0],
            "semantic_value": json.loads(key[1]),
            "before_bindings": left[key],
            "after_bindings": right[key],
            "gate": "BLOCK_SCOPE_REVIEW",
            "attribution": "NO_ATRIBUIBLE_SIN_VALIDACION_DE_AMBITO",
        }
        for key in sorted(left.keys() & right.keys())
        if left[key] != right[key]
    ]
