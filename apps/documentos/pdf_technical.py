"""Lossless commercial projection of extensible furniture JSON.

The projection retains source order, values and associations. Only internal
association keys are hidden; it never deduplicates or summarizes source text.
"""

from xml.sax.saxutils import escape

INTERNAL_KEYS = {"uid", "conjunto_uid", "componente_uid"}


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


def technical_entries(data, observations=None):
    """Return (kind, content) entries; rendering owns typography and pagination."""
    if not isinstance(data, dict):
        return [("text", value) for value in fields(data)]
    result = []
    general = data.get("caracteristicas_generales")
    general_entries = []
    if isinstance(general, dict):
        for key, value in general.items():
            if key == "dimensiones" and isinstance(value, dict):
                chips = [
                    rendered for name, dim in value.items() for rendered in fields(dim, label(name))
                ]
                if chips:
                    general_entries.append(("dimensions", chips))
            else:
                general_entries.extend(("text", rendered) for rendered in fields(value, label(key)))
    else:
        general_entries.extend(("text", value) for value in fields(general))
    # Unknown top-level commercial fields belong to GENERAL, not the image column.
    for key, value in data.items():
        if key not in INTERNAL_KEYS | {
            "caracteristicas_generales",
            "conjuntos",
            "componentes",
            "accesorios",
            "advertencias",
            "observaciones",
        }:
            general_entries.extend(("text", rendered) for rendered in fields(value, label(key)))
    if general_entries:
        result += [("section", "GENERAL"), *general_entries]

    sets = data.get("conjuntos") or []
    components = data.get("componentes") or []
    structure = []
    linked = set()
    if isinstance(sets, list):
        for group in sets:
            if not isinstance(group, dict):
                structure.extend(("text", value) for value in fields(group, "Conjunto"))
                continue
            if not present({k: v for k, v in group.items() if k not in INTERNAL_KEYS}):
                continue
            structure.append(("subsection", "Conjunto: " + text(group.get("nombre") or "")))
            structure.extend(
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
                    structure.extend(component_entries(component))
    else:
        structure.extend(("text", value) for value in fields(sets, "Conjuntos"))
    if isinstance(components, list):
        for index, component in enumerate(components):
            if index not in linked:
                structure.extend(component_entries(component))
    else:
        structure.extend(("text", value) for value in fields(components, "Componentes"))
    if structure:
        result += [("section", "ESTRUCTURA"), *structure]

    accessories = []
    for key in ("accesorios", "advertencias", "observaciones"):
        accessories.extend(("text", value) for value in fields(data.get(key), label(key)))
    accessories.extend(("text", value) for value in fields(observations, "Observaciones técnicas"))
    if accessories:
        result += [("section", "ACCESORIOS Y OBSERVACIONES DEL MUEBLE"), *accessories]
    return result


def component_entries(component):
    if isinstance(component, dict):
        entries = []
        if present(component.get("nombre")):
            entries.append(("subsection", text(component["nombre"])))
        entries.extend(
            ("text", value)
            for value in fields({k: v for k, v in component.items() if k != "nombre"})
        )
        return entries
    return [("text", value) for value in fields(component, "Componente")]
