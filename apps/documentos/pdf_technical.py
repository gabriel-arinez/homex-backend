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


def format_value(value):
    if isinstance(value, bool):
        return "Sí" if value else "No"
    return str(value)


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
        yield (f"<b>{text(prefix)}:</b> " if prefix else "") + text(format_value(value))


def catalog_measure(value, unit="mm"):
    if not present(value):
        return None
    from decimal import Decimal, InvalidOperation

    try:
        dec = Decimal(str(value))
        if dec.is_finite():
            formatted = (
                format(dec, "f").rstrip("0").rstrip(".").replace(".", ",")
                if "." in format(dec, "f")
                else str(dec)
            )
            return f"{formatted} {unit}" if unit else formatted
    except (InvalidOperation, ValueError, TypeError):
        pass
    return f"{value} {unit}" if unit else str(value)


def catalog_entries(detail):
    """Project catalogue product and line data into structured technical zones."""
    product = getattr(detail, "producto", None)
    if not product:
        return []

    chair = getattr(product, "productosilla", None)
    floor = getattr(product, "productopiso", None)
    category_obj = getattr(product, "categoria", None)
    category_code = getattr(category_obj, "codigo", None)
    if not category_code and getattr(detail, "tipo_item_id", None):
        category_code = getattr(detail.tipo_item, "codigo", None)

    result = []
    general_items = []
    characteristics = []
    dimensions = []

    def add_field(target, raw_val, field_label):
        val = getattr(raw_val, "nombre", raw_val)
        target.extend(fields(val, field_label))

    add_field(general_items, getattr(product, "sku", None), "SKU")

    familia = getattr(product, "familia", None)
    if present(getattr(familia, "nombre", None)):
        add_field(general_items, familia.nombre, "Familia")

    if chair or category_code == "SILLA":
        if chair:
            add_field(general_items, getattr(chair, "marca", None), "Marca")
            add_field(general_items, getattr(chair, "modelo", None), "Modelo")
            add_field(general_items, getattr(chair, "color_primario", None), "Color primario")
            add_field(general_items, getattr(chair, "color_secundario", None), "Color secundario")
            specs = getattr(chair, "especificaciones", None)
            if isinstance(specs, dict):
                for k, v in specs.items():
                    if k not in INTERNAL_KEYS:
                        characteristics.extend(fields(v, label(k)))
            elif present(specs):
                characteristics.extend(fields(specs, "Especificaciones"))
    elif floor or category_code == "PISO_FLOTANTE":
        if floor:
            add_field(general_items, getattr(floor, "marca", None), "Marca")
            add_field(general_items, getattr(floor, "modelo", None), "Modelo")
            add_field(characteristics, getattr(floor, "tipo", None), "Tipo")
            add_field(characteristics, getattr(floor, "material", None), "Material")
            add_field(characteristics, getattr(floor, "diseno", None), "Diseño")
            add_field(characteristics, getattr(floor, "acabado", None), "Acabado")
            espesor = catalog_measure(getattr(floor, "espesor_mm", None), "mm")
            if espesor:
                dimensions.extend(fields(espesor, "Espesor"))
            largo = catalog_measure(getattr(floor, "largo_mm", None), "mm")
            if largo:
                dimensions.extend(fields(largo, "Largo"))
            ancho = catalog_measure(getattr(floor, "ancho_mm", None), "mm")
            if ancho:
                dimensions.extend(fields(ancho, "Ancho"))
            rendimiento = catalog_measure(getattr(floor, "m2_por_caja", None), "m²")
            if rendimiento:
                dimensions.extend(fields(rendimiento, "Rendimiento por caja"))
    else:
        unidad_venta = getattr(product, "unidad_stock", None) or getattr(detail, "unidad", None)
        add_field(general_items, unidad_venta, "Unidad de venta")

    product_name = getattr(product, "nombre", None)
    if present(product_name) and product_name != getattr(detail, "nombre", None):
        add_field(general_items, product_name, "Producto de catálogo")

    for target_obj, known in (
        (
            product,
            {
                "id",
                "pk",
                "familia",
                "familia_id",
                "categoria",
                "categoria_id",
                "sku",
                "nombre",
                "precio_lista",
                "stock",
                "unidad_stock",
                "unidad_stock_id",
                "activo",
                "observaciones",
                "imagen_principal",
                "imagen_principal_variantes",
                "imagen_principal_dimensiones",
                "revision_humana_voz",
                "created_by",
                "created_by_id",
                "updated_by",
                "updated_by_id",
                "productosilla",
                "productopiso",
                "descuentoproducto",
                "imagenes",
                "demanda_pendiente_calculada",
            },
        ),
        (
            chair,
            {
                "producto",
                "producto_id",
                "marca",
                "marca_id",
                "modelo",
                "color_primario",
                "color_primario_id",
                "color_secundario",
                "color_secundario_id",
                "especificaciones",
                "created_by",
                "created_by_id",
                "updated_by",
                "updated_by_id",
            },
        ),
        (
            floor,
            {
                "producto",
                "producto_id",
                "marca",
                "marca_id",
                "modelo",
                "tipo",
                "tipo_id",
                "material",
                "material_id",
                "diseno",
                "diseno_id",
                "espesor_mm",
                "acabado",
                "acabado_id",
                "largo_mm",
                "ancho_mm",
                "m2_por_caja",
                "created_by",
                "created_by_id",
                "updated_by",
                "updated_by_id",
            },
        ),
    ):
        if target_obj is None:
            continue
        extra_dict = getattr(target_obj, "__dict__", {})
        for k, v in extra_dict.items():
            if (
                not k.startswith("_")
                and k not in known
                and k not in INTERNAL_KEYS
                and not callable(v)
            ):
                add_field(characteristics, v, label(k))

    if general_items:
        result += [("section", "INFORMACIÓN GENERAL"), ("characteristics", general_items)]
    if characteristics:
        section_title = (
            "ESPECIFICACIONES TÉCNICAS"
            if (chair or category_code == "SILLA")
            else "CARACTERÍSTICAS"
        )
        result += [("section", section_title), ("characteristics", characteristics)]
    if dimensions:
        result += [("section", "DIMENSIONES"), ("dimensions", dimensions)]

    notes, seen_notes = [], set()
    raw_desc = getattr(detail, "descripcion", None)
    if present(raw_desc) and str(raw_desc).strip() != str(getattr(detail, "nombre", "")).strip():
        for value in fields(raw_desc):
            clean = value.strip()
            if clean and clean not in seen_notes:
                seen_notes.add(clean)
                notes.append(clean)
    for value in fields(getattr(product, "observaciones", None)):
        clean = value.strip()
        if clean and clean not in seen_notes:
            seen_notes.add(clean)
            notes.append(clean)
    if notes:
        result += [("section", "OBSERVACIONES"), ("notes", notes)]

    return result


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
        unlinked = [c for index, c in enumerate(components) if index not in linked]
        unlinked.sort(
            key=lambda c: (
                0
                if isinstance(c, dict)
                and str(c.get("nombre") or "").strip().lower() == "estructura"
                else 1
            )
        )
        for component in unlinked:
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
    notes, seen_notes = [], set()
    for value in (
        *fields(data.get("advertencias")),
        *fields(data.get("observaciones")),
        *fields(observations),
    ):
        clean_note = value.strip()
        if clean_note and clean_note not in seen_notes:
            seen_notes.add(clean_note)
            notes.append(clean_note)
    if notes:
        result += [("section", "OBSERVACIONES DEL MUEBLE"), ("notes", notes)]
    return result


def component_entries(component):
    if isinstance(component, dict):
        name = str(component.get("nombre") or "").strip()
        attrs = {k: v for k, v in component.items() if k != "nombre"}
        content_fields = [f"• {v}" for v in fields(attrs)]
        if name.lower() == "estructura":
            return (
                [("text", v) for v in content_fields]
                if content_fields
                else [("text", "• Estructura")]
            )
        entries = []
        if name:
            entries.append(("subsection", text(name.upper())))
        entries.extend(("text", v) for v in content_fields)
        return entries
    return [("text", f"• {v}") for v in fields(component)]
