"""Proyección única de evidencia NLP a un borrador PRF-03, nunca escritura comercial."""

import re
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from homex_nlp.contracts import ExtractionResult, Measurement

from apps.catalogo.atributos_mueble import normalizar
from apps.catalogo.models import MetadatoAtributoMueble, ValorCatalogo
from apps.proformas.validacion_tecnica import validar_datos_tecnicos

VERSION_PROYECCION = "PRF04_2"


def proyectar(raw):
    resultado = ExtractionResult.model_validate(raw)
    item = resultado.item_proposal
    if resultado.status != "REQUIRES_REVIEW" or item is None or not item.name:
        return None
    espesores_pendientes = []
    for c in resultado.candidates:
        if c.label != "ESPESOR" or c.candidate_id not in item.unresolved:
            continue
        value = c.normalized_value
        if not isinstance(value, list) or len(value) != 2:
            continue
        try:
            measure = Measurement(
                value=value[0], unit=value[1], original_text=c.text, evidence_ids=[c.candidate_id]
            )
        except ValueError:
            continue
        espesores_pendientes.append(measure)
    has_lexical_recovery = any(
        c.label == "RECUPERACION_LEXICA" and c.decision != "REJECTED" for c in resultado.candidates
    )

    def _humanize_warning_message(warning):
        msg = warning.message
        if msg.startswith("Confirm contextual interpretation of "):
            m = re.match(r"Confirm contextual interpretation of '(.+)' as '(.+)'\.", msg)
            if m:
                return f"Se interpretó «{m.group(1)}» como «{m.group(2)}»; confirma si es correcto."
            return "Se interpretó un término ambiguo; confirma si es correcto."
        if msg.startswith("Explicit atypical dimension retained: "):
            detail = (
                msg.removeprefix("Explicit atypical dimension retained: ").split(";")[0].strip()
            )
            return f"Se conservó una medida atípica ({detail}); confirma si corresponde al mueble."
        if msg == "Accessory quantity requires review.":
            return "Revisa la cantidad de los accesorios antes de confirmar."
        if msg.startswith("Noncommercial test or retrospective context"):
            return "Contexto no comercial; no se generó una propuesta de mueble."
        if msg == "Confirm the thickness unit.":
            return "Confirma la unidad del espesor antes de aplicar."
        # Nunca exponer estructuras internas ni diagnósticos técnicos en inglés.
        forbidden = (
            "{",
            "}",
            "→",
            "UNRESOLVED",
            "component_ref",
            "Internal ",
            "Confirm ",
            "requires review",
            "Explicit ",
        )
        if any(token in msg for token in forbidden):
            fallback_by_code = {
                "CONFLICTING_VALUES": "Hay valores por aclarar; revísalos antes de confirmar.",
                "UNKNOWN_TERM": "Se detectó un término por confirmar; revisa la interpretación.",
                "REQUIRED_FIELD_MISSING": "Falta un dato requerido por completar.",
                "INVALID_PRICE": "Revisa el precio dictado antes de confirmar.",
            }
            return fallback_by_code.get(
                warning.code, "Revisa este dato antes de confirmar el mueble."
            )
        return msg

    pendientes = [
        {"codigo": w.code, "ruta": w.path, "mensaje": _humanize_warning_message(w)}
        for w in resultado.warnings
        if w.severity != "INFO"
        and w.code not in {"MISSING_UNIT", "MISSING_AXIS"}
        and not (w.code == "UNKNOWN_TERM" and w.path == "/candidates" and has_lexical_recovery)
        # El pendiente de espesor se reconstruye abajo con resolución tipada.
        # No duplicarlo con un aviso genérico que el configurador no puede cerrar.
        and not (
            w.code == "REQUIRED_FIELD_MISSING"
            and w.path == "/item_proposal/thicknesses"
            and (
                espesores_pendientes
                or any(
                    t.component_ref not in {c.component_id for c in item.components}
                    for t in item.thicknesses
                )
            )
        )
    ]
    generales = {}
    conflictivos = set()

    def registrar(destino, campo, valor, ambito):
        clave = (ambito, campo)
        if clave in conflictivos:
            return

        def comparable(value):
            value = normalizar(value)
            if campo == "material":
                value = re.sub(r"\bmelamine\b", "melamina", value)
            return value

        if campo in destino and comparable(destino[campo]) == comparable(valor):
            return
        if campo in destino and destino[campo] != valor:
            destino.pop(campo)
            conflictivos.add(clave)
            nombre = componentes[ambito]["nombre"] if ambito in componentes else "el mueble"
            pendientes.append(
                {
                    "codigo": "CONFLICTING_VALUES",
                    "ruta": f"{ambito}.{campo}",
                    "mensaje": f"Aclare {campo} en {nombre}.",
                    "resolucion": (
                        {"tipo": "COMPONENTE", "uid": componentes[ambito]["uid"], "campo": campo}
                        if ambito in componentes
                        else {"tipo": "ATRIBUTO_GENERAL", "clave": campo}
                    ),
                }
            )
        else:
            destino[campo] = valor

    componentes = {
        c.component_id: {
            "uid": str(uuid5(NAMESPACE_URL, f"{resultado.request_id}/{c.component_id}")),
            "nombre": c.name,
        }
        for c in item.components
    }
    evidence = {candidate.candidate_id: candidate for candidate in resultado.candidates}

    def inferred_measurement(measurement):
        return any(
            isinstance(evidence[ref].normalized_value, dict)
            and (
                evidence[ref].normalized_value.get("unit_inferred") is True
                or evidence[ref].normalized_value.get("unit_basis") == "shared_enumeration"
            )
            for ref in measurement.evidence_ids
            if ref in evidence
        )

    def suggested_measurement(measurement):
        return f"{measurement.value} {measurement.unit}"

    dimensiones = {}
    inferred_chain = []
    ejes_conflictivos = set()
    pendientes_medidas = {}
    for medida in item.dimensions:
        if inferred_measurement(medida):
            if not medida.axis and not medida.component_ref:
                inferred_chain.append(medida)
                continue
            pendientes.append(
                {
                    "codigo": "MISSING_UNIT",
                    "ruta": "dimensiones",
                    "mensaje": (
                        f"Unidad inferida: se propone {suggested_measurement(medida)} "
                        f"para {medida.axis or medida.original_text}; confirme valor, eje y unidad."
                    ),
                    "resolucion": (
                        {
                            "tipo": "COMPONENTE",
                            "uid": componentes[medida.component_ref]["uid"],
                            "campo": "dimensiones",
                            **({"valor": medida.axis} if medida.axis else {}),
                        }
                        if medida.component_ref in componentes
                        else {"tipo": "DIMENSION", "clave": medida.axis}
                        if medida.axis
                        else {"tipo": "DIMENSIONES_NUEVAS", "cantidad": 1}
                    ),
                }
            )
            continue
        if medida.axis and medida.unit and medida.component_ref in componentes:
            pieza = componentes[medida.component_ref]
            valor = f"{medida.axis}: {medida.value} {medida.unit}"
            pieza["dimensiones"] = "; ".join(filter(None, [pieza.get("dimensiones"), valor]))
        elif medida.axis and medida.unit and not medida.component_ref:
            if medida.axis in ejes_conflictivos:
                continue
            if medida.axis in dimensiones:
                pendientes.append(
                    {
                        "codigo": "CONFLICTING_VALUES",
                        "ruta": "dimensiones",
                        "mensaje": f"Aclare la medida de {medida.axis}.",
                        "resolucion": {"tipo": "DIMENSION", "clave": medida.axis},
                    }
                )
                dimensiones.pop(medida.axis)
                ejes_conflictivos.add(medida.axis)
                continue
            dimensiones[medida.axis] = {"valor": medida.value, "unidad": medida.unit}
        else:
            pendiente_medida = {
                "codigo": "MISSING_UNIT" if medida.axis and not medida.unit else "MISSING_AXIS",
                "ruta": "dimensiones",
                "mensaje": f"Complete el ámbito/eje/unidad de {medida.original_text}.",
                "resolucion": (
                    {
                        "tipo": "COMPONENTE",
                        "uid": componentes[medida.component_ref]["uid"],
                        "campo": "dimensiones",
                    }
                    if medida.component_ref in componentes
                    else {"tipo": "DIMENSION", "clave": medida.axis}
                    if medida.axis
                    else {"tipo": "DIMENSIONES_NUEVAS", "cantidad": 1}
                ),
            }
            pendientes.append(pendiente_medida)
            pendientes_medidas[id(medida)] = pendiente_medida
    if inferred_chain:
        # Unit inference never supplies an axis. Keep the existing aggregate
        # review action so both L arms require distinct human-confirmed measures.
        pendientes.append(
            {
                "codigo": "MISSING_AXIS",
                "ruta": "dimensiones",
                "mensaje": (
                    "Unidad inferida: se proponen "
                    + "; ".join(suggested_measurement(m) for m in inferred_chain)
                    + "; confirme valores, ejes y unidades."
                ),
                "resolucion": {"tipo": "DIMENSIONES_NUEVAS", "cantidad": len(inferred_chain)},
            }
        )
    for candidato in resultado.candidates:
        if candidato.candidate_id in item.unresolved and candidato.label == "DIMENSION":
            # NLP0.1.25 preserves both scalar measurements and whole-chain
            # evidence. Missing axes already have typed pending resolutions
            # above; do not request the same dimensions a second time.
            medidas_cadena = [
                medida
                for medida in item.dimensions
                if candidato.candidate_id in medida.evidence_ids
            ]
            if medidas_cadena and all(inferred_measurement(m) for m in medidas_cadena):
                continue  # The typed suggestions above already retain this chain.
            cantidad_cadena = len(re.split(r"[x×]", candidato.text, flags=re.I))
            if cantidad_cadena not in {2, 3}:
                cantidad_cadena = 2  # Preserve the legacy unresolved-pair fallback.
            if len(medidas_cadena) == cantidad_cadena and all(
                not (
                    medida.axis
                    and medida.unit
                    and (not medida.component_ref or medida.component_ref in componentes)
                )
                for medida in medidas_cadena
            ):
                if all(medida.component_ref in componentes for medida in medidas_cadena):
                    continue  # Component fields already have scoped resolutions.
                if all(not medida.axis and not medida.component_ref for medida in medidas_cadena):
                    # Vue evaluates each request against a global new-measure
                    # count; N requests of1 do NOT require N distinct measures.
                    # Replace scalar root prompts with one complete-chain count.
                    individuales = {id(pendientes_medidas[id(m)]) for m in medidas_cadena}
                    pendientes[:] = [p for p in pendientes if id(p) not in individuales]
            pendientes.append(
                {
                    "codigo": "MISSING_AXIS",
                    "ruta": "dimensiones",
                    "mensaje": f"Indique ejes y unidades de {candidato.text}.",
                    "resolucion": {"tipo": "DIMENSIONES_NUEVAS", "cantidad": cantidad_cadena},
                }
            )
    if dimensiones:
        generales["dimensiones"] = dimensiones
    for medida in [*item.thicknesses, *espesores_pendientes]:
        if inferred_measurement(medida):
            shared_unit = any(
                ref in evidence
                and isinstance(evidence[ref].normalized_value, dict)
                and evidence[ref].normalized_value.get("unit_basis") == "shared_enumeration"
                for ref in medida.evidence_ids
            )
            unit_basis = (
                "Unidad compartida por enumeración"
                if shared_unit
                else "Unidad inferida por contexto"
            )
            pendientes.append(
                {
                    "codigo": "ESPESOR_SIN_COMPONENTE",
                    "ruta": "especificacion.datos_tecnicos.componentes",
                    "mensaje": (
                        f"{unit_basis}: se propone "
                        f"{suggested_measurement(medida)} "
                        "de espesor; confirme unidad y asociación antes de aplicarlo."
                        + "".join(
                            f" Espesor explícito conservado: {suggested_measurement(other)}."
                            for other in item.thicknesses
                            if other.component_ref == medida.component_ref
                            and not inferred_measurement(other)
                        )
                    ),
                    "resolucion": {
                        "tipo": "ESPESOR_SIN_COMPONENTE",
                        "valor": suggested_measurement(medida),
                    },
                }
            )
            continue
        if medida.component_ref in componentes and medida.unit:
            registrar(
                componentes[medida.component_ref],
                "espesor",
                f"{medida.value} {medida.unit}",
                medida.component_ref,
            )
            continue

        aviso = {
            "codigo": "ESPESOR_SIN_COMPONENTE",
            "ruta": "especificacion.datos_tecnicos.componentes",
            "mensaje": (
                f"El espesor {medida.original_text} no tiene una pieza "
                "identificada de forma confiable. Revise su asociación "
                "antes de confirmar el mueble."
            ),
        }
        if medida.unit:
            aviso["resolucion"] = {
                "tipo": "ESPESOR_SIN_COMPONENTE",
                "valor": f"{medida.value} {medida.unit}",
            }
        pendientes.append(aviso)
    colors = [color for color in (item.primary_color, item.secondary_color) if color]
    if len(colors) == 2 and colors[0].component_ref == colors[1].component_ref:
        ref = colors[0].component_ref
        if ref in componentes:
            registrar(componentes[ref], "color", " con ".join(c.value for c in colors), ref)
        elif ref is None:
            # Existing legacy consumers read these roles, while the studio renders
            # their consistent attribute representations without catalog lookups.
            for field, name, color in zip(
                ("color_principal", "color_secundario"),
                ("Color principal", "Color secundario"),
                colors,
                strict=True,
            ):
                generales[field] = color.value
                generales.setdefault("atributos", []).append({"nombre": name, "valor": color.value})
    else:
        for color in colors:
            destino = componentes.get(color.component_ref) if color.component_ref else generales
            if destino is not None:
                registrar(destino, "color", color.value, color.component_ref or "general")
    colores_proyectados = {
        evidencia
        for color in (item.primary_color, item.secondary_color)
        if color
        for evidencia in color.evidence_ids
    }
    # El contrato v1 admite relaciones explícitas a través de candidatos tipados.
    for candidato in resultado.candidates:
        if candidato.decision != "ACCEPTED":
            continue
        destino = componentes.get(candidato.component_ref) if candidato.component_ref else generales
        if destino is None:
            continue
        # La evidencia de un color tipado ya se registró con su valor canónico.
        # No enfrentar su texto literal (blanca) contra ese mismo valor (blanco).
        if candidato.label == "COLOR" and candidato.candidate_id in colores_proyectados:
            continue
        if candidato.label in {"MATERIAL", "COLOR", "ACABADO"}:
            registrar(
                destino,
                candidato.label.lower(),
                candidato.normalized_value
                if candidato.label == "COLOR" and isinstance(candidato.normalized_value, str)
                else candidato.text,
                candidato.component_ref or "general",
            )
        if candidato.label == "MARCA" and isinstance(candidato.normalized_value, str):
            attribute = {"nombre": "Marca", "valor": candidato.normalized_value}
            attributes = destino.setdefault("atributos", [])
            if attribute not in attributes:
                attributes.append(attribute)
        if candidato.label == "CANTIDAD_INTERNA" and candidato.component_ref:
            valor = candidato.normalized_value
            if type(valor) is int and valor > 0:
                destino["cantidad_interna"] = valor
    review_codes = {
        "RECUPERACION_LEXICA",
        "ESPECIFICACION",
        "GEOMETRIA",
        "RANGO_DIMENSIONAL",
        "DISTRIBUCION",
        "SELECCION_COLOR",
        "COLOR_NO_RESUELTO",
    }
    for candidate in resultado.candidates:
        if candidate.label not in review_codes or candidate.decision == "REJECTED":
            continue
        value = candidate.normalized_value
        if candidate.label == "RECUPERACION_LEXICA":
            target_text = str(value or candidate.text)
            reason = candidate.reason or ""
            comp = componentes.get(candidate.component_ref) if candidate.component_ref else None
            if "counted_furniture_identity" in reason:
                pendientes.append(
                    {
                        "codigo": candidate.label,
                        "ruta": "nombre",
                        "mensaje": (
                            f"Se interpretó «{candidate.text}» como «{target_text}» "
                            "en el nombre del mueble; confirma si es correcto."
                        ),
                    }
                )
            elif "explicit_decorative_color" in reason:
                if comp:
                    pendientes.append(
                        {
                            "codigo": candidate.label,
                            "ruta": f"{candidate.component_ref}.color",
                            "mensaje": (
                                f"Se interpretó «{candidate.text}» como «{target_text}» "
                                f"en {comp['nombre']}; confirma el color."
                            ),
                            "resolucion": {
                                "tipo": "COMPONENTE",
                                "uid": comp["uid"],
                                "campo": "color",
                            },
                        }
                    )
                else:
                    pendientes.append(
                        {
                            "codigo": candidate.label,
                            "ruta": "general.color",
                            "mensaje": (
                                f"Se interpretó «{candidate.text}» como «{target_text}»; "
                                "confirma el color."
                            ),
                            "resolucion": {"tipo": "ATRIBUTO_GENERAL", "clave": "color"},
                        }
                    )
            elif "board_brand_context" in reason:
                has_brand = any(
                    a.get("nombre", "").lower() == "marca" for a in generales.get("atributos", [])
                )
                pendientes.append(
                    {
                        "codigo": candidate.label,
                        "ruta": "general.marca" if has_brand else "especificacion.observaciones",
                        "mensaje": (
                            f"Se interpretó «{candidate.text}» como marca «{target_text}»; "
                            "confirma si es correcto."
                        ),
                        "resolucion": (
                            {"tipo": "ATRIBUTO_GENERAL", "clave": "marca"}
                            if has_brand
                            else {"tipo": "OBSERVACIONES"}
                        ),
                    }
                )
            elif "technical_material_phrase" in reason and comp:
                pendientes.append(
                    {
                        "codigo": candidate.label,
                        "ruta": f"{candidate.component_ref}.material",
                        "mensaje": (
                            f"Se interpretó «{candidate.text}» como «{target_text}» "
                            f"en {comp['nombre']}; confirma si es correcto."
                        ),
                        "resolucion": {
                            "tipo": "COMPONENTE",
                            "uid": comp["uid"],
                            "campo": "material",
                        },
                    }
                )
            elif "technical_material_phrase" in reason:
                pendientes.append(
                    {
                        "codigo": candidate.label,
                        "ruta": "general.material",
                        "mensaje": (
                            f"Se interpretó «{candidate.text}» como «{target_text}»; "
                            "confirma el material."
                        ),
                        "resolucion": {"tipo": "ATRIBUTO_GENERAL", "clave": "material"},
                    }
                )
            else:
                pendientes.append(
                    {
                        "codigo": candidate.label,
                        "ruta": "especificacion.observaciones",
                        "mensaje": (
                            f"Se interpretó «{candidate.text}» como «{target_text}»; "
                            "confirma si es correcto."
                        ),
                        "resolucion": {"tipo": "OBSERVACIONES"},
                    }
                )
        elif candidate.label == "ESPECIFICACION":
            detail = str(value or candidate.text).strip()
            pendientes.append(
                {
                    "codigo": candidate.label,
                    "ruta": "especificacion.observaciones",
                    "mensaje": (
                        f"Detalle adicional detectado: «{detail}». Revísalo en Observaciones."
                    ),
                    "resolucion": {"tipo": "OBSERVACIONES"},
                }
            )
        elif candidate.label == "GEOMETRIA":
            pendientes.append(
                {
                    "codigo": candidate.label,
                    "ruta": "especificacion.observaciones",
                    "mensaje": "Mueble en L: confirma la orientación y los ejes de las medidas.",
                    "resolucion": {"tipo": "OBSERVACIONES"},
                }
            )
        elif candidate.label == "RANGO_DIMENSIONAL":
            if isinstance(value, dict):
                axis = value.get("axis") or "medida"
                low = value.get("minimum", "")
                high = value.get("maximum", "")
                unit = value.get("unit", "")
                msg = (
                    f"Rango de {axis} detectado (de {low} a {high} {unit}). "
                    "Confirma la medida final en Observaciones."
                )
            else:
                msg = (
                    f"Rango dimensional detectado («{candidate.text}»). Confirma en Observaciones."
                )
            pendientes.append(
                {
                    "codigo": candidate.label,
                    "ruta": "especificacion.observaciones",
                    "mensaje": msg,
                    "resolucion": {"tipo": "OBSERVACIONES"},
                }
            )
        elif candidate.label == "DISTRIBUCION":
            count = value.get("count") if isinstance(value, dict) else None
            comp = componentes.get(candidate.component_ref) if candidate.component_ref else None
            if comp and count is not None:
                pendientes.append(
                    {
                        "codigo": candidate.label,
                        "ruta": "especificacion.datos_tecnicos.componentes",
                        "mensaje": (
                            f"Se mencionaron {count} por lado en {comp['nombre']}; "
                            "indica la cantidad total."
                        ),
                        "resolucion": {
                            "tipo": "COMPONENTE",
                            "uid": comp["uid"],
                            "campo": "cantidad_interna",
                        },
                    }
                )
            else:
                pendientes.append(
                    {
                        "codigo": candidate.label,
                        "ruta": "especificacion.observaciones",
                        "mensaje": (
                            f"Distribución mencionada («{candidate.text}»); "
                            "confirma la cantidad total en Observaciones."
                        ),
                        "resolucion": {"tipo": "OBSERVACIONES"},
                    }
                )
        elif candidate.label == "SELECCION_COLOR":
            pendientes.append(
                {
                    "codigo": candidate.label,
                    "ruta": "general.color",
                    "mensaje": (
                        "Color a elección: selecciona o confirma el color cuando esté definido."
                    ),
                    "resolucion": {"tipo": "ATRIBUTO_GENERAL", "clave": "color"},
                }
            )
        elif candidate.label == "COLOR_NO_RESUELTO":
            color_text = str(value or candidate.text).strip()
            pendientes.append(
                {
                    "codigo": candidate.label,
                    "ruta": "general.color",
                    "mensaje": (
                        f"Color «{color_text}» no reconocido automáticamente; "
                        "selecciona o aclara el color."
                    ),
                    "resolucion": {"tipo": "ATRIBUTO_GENERAL", "clave": "color"},
                }
            )
    # Los atributos generales se editan en el mismo arreglo dinámico PRF-03.
    catalogo = list(
        MetadatoAtributoMueble.objects.select_related("valor").filter(valor__activo=True)
    )
    for campo in ("material", "espesor", "color", "acabado"):
        if campo not in generales:
            continue
        valor = generales.pop(campo)
        matches = [
            m
            for m in catalogo
            if campo
            in {
                normalizar(m.valor.nombre),
                normalizar(m.valor.codigo),
                *(normalizar(str(s)) for s in m.sinonimos),
            }
        ]
        atributo = {"nombre": campo.capitalize(), "valor": valor}
        if len(matches) == 1:
            atributo.update(
                codigo=matches[0].valor.codigo,
                nombre=matches[0].valor.nombre,
                tipo_entrada=matches[0].tipo_entrada,
            )
        generales.setdefault("atributos", []).append(atributo)
    grupos = {}
    for candidato in resultado.candidates:
        value = candidato.normalized_value
        if (
            candidato.label == "CONJUNTO"
            and candidato.decision == "ACCEPTED"
            and isinstance(value, dict)
        ):
            if isinstance(value.get("group_id"), str) and isinstance(value.get("name"), str):
                grupos[value["group_id"]] = {
                    "uid": str(uuid5(NAMESPACE_URL, f"{resultado.request_id}/{value['group_id']}")),
                    "nombre": value["name"],
                }
    for candidato in resultado.candidates:
        value = candidato.normalized_value
        if (
            candidato.label == "COMPONENTE"
            and candidato.decision == "ACCEPTED"
            and isinstance(value, dict)
            and value.get("conjunto_ref") in grupos
            and candidato.component_ref in componentes
        ):
            componentes[candidato.component_ref]["conjunto_uid"] = grupos[value["conjunto_ref"]][
                "uid"
            ]
    # Conservar el ámbito explícito del productor; no inferir una pieza ni cantidad.
    accesorios_globales = []
    accesorios_por_componente = {}
    for accesorio in item.accessories:
        valor = (
            f"{accesorio.quantity} {accesorio.name}"
            if accesorio.quantity is not None
            else accesorio.name
        )
        if not accesorio.component_ref:
            accesorios_globales.append(valor)
        elif accesorio.component_ref in componentes:
            accesorios_por_componente.setdefault(accesorio.component_ref, []).append(valor)
        else:
            pendientes.append(
                {
                    "codigo": "ACCESORIO_SIN_COMPONENTE",
                    "ruta": "especificacion.datos_tecnicos.componentes",
                    "mensaje": f"Revise el componente del accesorio {valor} antes de confirmar.",
                }
            )
    for referencia, valores in accesorios_por_componente.items():
        componentes[referencia].setdefault("atributos", []).append(
            {"nombre": "Accesorios", "valor": "; ".join(valores)}
        )
    grupos_usados = {c.get("conjunto_uid") for c in componentes.values()}
    datos = {
        "caracteristicas_generales": generales,
        "conjuntos": [g for g in grupos.values() if g["uid"] in grupos_usados],
        "componentes": list(componentes.values()),
        "accesorios": accesorios_globales,
        "descripcion_original": resultado.text_original,
    }
    validar_datos_tecnicos(datos)
    termino = normalizar(item.furniture_type_candidate or item.name)
    # Variantes de categorías existentes; los IDs siempre proceden de la BD.
    # Velador, atril y recepción no tienen equivalencia aprobada en el catálogo.
    variantes = (
        (
            r"(?:escritorios?(?: operativos?| ejecutivos?| rectos?)?|escritor ejecutivo)"
            r"(?: en (?:l|ele))?",
            "escritorio",
        ),
        (r"mesas? de reunion", "mesa de reunion"),
        (r"(?:gabeteros?|gaveteros?)(?: moviles?)?", "gavetero"),
        (r"credenzas?", "credenza"),
        (r"estantes?(?: de pared)?", "estante"),
    )
    for patron, canonico in variantes:
        if re.fullmatch(patron, termino):
            termino = canonico
            break
    tipos = [
        v
        for v in ValorCatalogo.objects.filter(concepto__codigo="TIPO_MUEBLE", activo=True)
        if normalizar(v.nombre) == termino or normalizar(v.codigo) == termino
    ]
    tipo = tipos[0].id if len(tipos) == 1 else None
    if tipo is None:
        pendientes.append(
            {
                "codigo": "TIPO_NO_RESUELTO",
                "ruta": "especificacion.tipo_mueble",
                "mensaje": f"Seleccione el tipo de mueble para {item.name}.",
            }
        )
    precio = item.price
    precio_unitario = (
        precio.unit_price_input if precio and precio.mode == "PRECIO_UNITARIO" else None
    )
    total_explicito = precio.line_total if precio and precio.mode == "TOTAL_NEGOCIADO" else None
    if precio and precio.mode == "PRECIO_UNITARIO":
        totales = {
            c.normalized_value
            for c in resultado.candidates
            if c.label == "PRECIO_TOTAL"
            and c.decision == "ACCEPTED"
            and isinstance(c.normalized_value, str)
        }
        if len(totales) == 1:
            total_explicito = next(iter(totales))
    if total_explicito is not None:
        pendientes.append(
            {
                "codigo": "TOTAL_NEGOCIADO",
                "ruta": "comercial.precio_unitario",
                "total_negociado": total_explicito,
                "moneda_codigo": precio.currency,
                "mensaje": (
                    f"Total dictado {total_explicito} {precio.currency}; "
                    "revise su relación con cantidad y precio unitario."
                ),
            }
        )
    for candidate in resultado.candidates:
        if candidate.label != "PRECIO_AMBIGUO" or candidate.decision != "UNRESOLVED":
            continue
        equivalence = item.quantity == 1 and "equivalence" in (candidate.reason or "")
        # A suggestion remains unresolved evidence, never an explicitly spoken mode.
        # Only the extractor's explicit root quantity can establish this equivalence.
        if equivalence and precio_unitario is None:
            precio_unitario = format(Decimal(str(candidate.normalized_value)), ".2f")
        pendientes.append(
            {
                "codigo": "PRECIO_AMBIGUO",
                "ruta": "comercial.precio_unitario",
                "mensaje": (
                    f"Importe dictado {candidate.normalized_value}; "
                    + (
                        "equivalencia aritmética entre unitario y total para cantidad uno, "
                        "no modalidad explícita. "
                        if equivalence
                        else "modalidad comercial ambigua. "
                    )
                    + "Confirme moneda, importe y modalidad antes de aplicar el precio."
                ),
            }
        )
    unidades = [
        c
        for c in resultado.candidates
        if c.label == "UNIDAD_MEDIDA"
        and c.decision == "ACCEPTED"
        and isinstance(c.normalized_value, str)
        and c.normalized_value in {"PIEZA", "JUEGO"}
    ]
    descuentos = [
        c.normalized_value
        for c in resultado.candidates
        if c.label == "DESCUENTO"
        and c.decision == "ACCEPTED"
        and isinstance(c.normalized_value, str)
    ]
    return {
        "version_proyeccion": VERSION_PROYECCION,
        "comercial": {
            "nombre": item.name,
            "cantidad": item.quantity,
            "unidad_codigo": unidades[0].normalized_value if len(unidades) == 1 else None,
            "precio_unitario": precio_unitario,
            "descuento": descuentos[0] if len(descuentos) == 1 else None,
        },
        "especificacion": {
            "tipo_mueble": tipo,
            "datos_tecnicos": datos,
            "observaciones": item.observations,
        },
        "pendientes": pendientes,
    }
