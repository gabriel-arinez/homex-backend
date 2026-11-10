"""Lossless commercial projection of extensible furniture JSON.

The projection retains source order, values and associations. Only evidenced operational
keys are hidden. Proven duplicate source clauses are suppressed, never summarized.
"""

from xml.sax.saxutils import escape

INTERNAL_KEYS = {"uid", "conjunto_uid", "componente_uid", "tipo_entrada"}


def present(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return False
    if isinstance(value, (list, dict)):
        return any(present(v) for v in (value.values() if isinstance(value, dict) else value))
    return True


def text(value):
    return escape(str(value)).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br/>")


def label(key):
    return str(key).replace("_", " ").capitalize()


def fields(value, prefix=""):
    """Yield readable, recursively labelled values without a raw JSON repr."""
    if not present(value):
        return
    if isinstance(value, dict):
        if "valor" in value:
            if present(value["valor"]):
                name = value.get("nombre") or prefix
                suffix = f" {text(value['unidad'])}" if present(value.get("unidad")) else ""
                for rendered in fields(value["valor"]):
                    yield (f"<b>{text(name)}:</b> " if name else "") + rendered + suffix
            for key, child in value.items():
                if key not in INTERNAL_KEYS | {"nombre", "valor", "unidad", "codigo"}:
                    yield from fields(child, label(key))
        else:
            for key, child in value.items():
                if key not in INTERNAL_KEYS:
                    path = f"{prefix} / {label(key)}" if prefix else label(key)
                    yield from fields(child, path)
    elif isinstance(value, list):
        for child in value:
            yield from fields(child, prefix)
    else:
        yield (f"<b>{text(prefix)}:</b> " if prefix else "") + text(value)


def technical_entries(data, observations=None, description=None, product_name=None):
    """Project source associations into independent, dynamically measured zones."""
    from apps.documentos.pdf_source import additional_source

    if not isinstance(data, dict):
        return [("text", value) for value in fields(data)]
    result, general_entries, characteristics = [], [], []
    general = data.get("caracteristicas_generales")
    if isinstance(general, dict):
        for key, value in general.items():
            if key in INTERNAL_KEYS or (key == "nombre" and value == product_name):
                continue
            values = list(fields(value, "" if key == "dimensiones" else label(key)))
            if key == "dimensiones" and values:
                general_entries += [("section", "DIMENSIONES"), ("dimensions", values)]
            else:
                characteristics.extend(values)
    else:
        characteristics.extend(fields(general))
    for key, value in data.items():
        if key not in INTERNAL_KEYS | {
            "caracteristicas_generales",
            "conjuntos",
            "componentes",
            "accesorios",
            "advertencias",
            "observaciones",
            "descripcion_original",
        }:
            if key != "nombre" or value != product_name:
                characteristics.extend(fields(value, label(key)))
    if characteristics:
        general_entries += [("section", "CARACTERÍSTICAS"), ("characteristics", characteristics)]
    # Both source fields can contain capture dictation. Compare each against
    # structured descriptions, not each other. Deduplicate complete retained
    # contexts only: merging individual clauses would detach shared wording
    # from different component headings across the two source fields.
    additional, emitted_contexts = [], set()
    for source in (
        description if description != product_name else None,
        data.get("descripcion_original"),
    ):
        context = tuple(additional_source(source, data, (observations,), product_name=product_name))
        if context not in emitted_contexts:
            emitted_contexts.add(context)
            additional.extend(context)
    if general_entries:
        result += general_entries

    sets = data.get("conjuntos") or []
    components = data.get("componentes") or []
    groups, linked = [], set()
    if isinstance(sets, list):
        for group in sets:
            if not isinstance(group, dict):
                groups.append([("text", value) for value in fields(group, "Conjunto")])
                continue
            if not present({k: v for k, v in group.items() if k not in INTERNAL_KEYS}):
                continue
            entries = [("subsection", "Conjunto: " + text(group.get("nombre") or ""))]
            entries.extend(
                ("text", value)
                for value in fields({k: v for k, v in group.items() if k != "nombre"})
            )
            for index, component in enumerate(components if isinstance(components, list) else []):
                if (
                    isinstance(component, dict)
                    and present(group.get("uid"))
                    and component.get("conjunto_uid") == group["uid"]
                ):
                    linked.add(index)
                    entries.extend(component_entries(component))
            groups.append(entries)
    else:
        groups.append([("text", value) for value in fields(sets, "Conjuntos")])
    if isinstance(components, list):
        for index, component in enumerate(components):
            if index not in linked:
                groups.append(component_entries(component))
    else:
        groups.append([("text", value) for value in fields(components, "Componentes")])
    groups = [group for group in groups if group]
    if groups:
        result += [("section", "ESTRUCTURA"), ("groups", groups)]

    # Resolve associations before suppressing their operational identifiers.
    names = {
        obj.get("uid"): obj.get("nombre", "")
        for obj in [
            *(sets if isinstance(sets, list) else []),
            *(components if isinstance(components, list) else []),
        ]
        if isinstance(obj, dict) and obj.get("uid")
    }
    accessories = []
    values = data.get("accesorios") or []
    for accessory in values if isinstance(values, list) else [values]:
        association = []
        if isinstance(accessory, dict):
            association = [
                names[accessory[key]]
                for key in ("conjunto_uid", "componente_uid")
                if accessory.get(key) in names
            ]
        prefix = " / ".join(association)
        accessories.append(
            [
                ("text", (f"<b>{text(prefix)}:</b> " if prefix else "") + value)
                for value in fields(accessory)
            ]
        )
    if any(accessories):
        result += [("section", "ACCESORIOS"), ("groups", accessories)]
    notes = [
        value
        for key in ("advertencias", "observaciones")
        for value in fields(data.get(key), label(key))
    ]
    notes.extend(fields(observations, "Observaciones técnicas"))
    if additional:
        notes.append("<br/>".join(text(part) for part in additional))
    if notes:
        result += [("section", "OBSERVACIONES DEL MUEBLE"), ("notes", notes)]
    return result


def component_entries(component):
    if isinstance(component, dict):
        entries = []
        if present(component.get("nombre")):
            entries.append(("subsection", "• Componente: " + text(component["nombre"])))
        entries.extend(
            ("text", value)
            for value in fields({k: v for k, v in component.items() if k != "nombre"})
        )
        return entries
    return [("text", value) for value in fields(component, "Componente")]
