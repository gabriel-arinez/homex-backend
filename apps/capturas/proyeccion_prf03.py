"""Proyección única de evidencia NLP a un borrador PRF-03, nunca escritura comercial."""

from uuid import NAMESPACE_URL, uuid5

from homex_nlp.contracts import ExtractionResult

from apps.catalogo.atributos_mueble import normalizar
from apps.catalogo.models import MetadatoAtributoMueble, ValorCatalogo
from apps.proformas.validacion_tecnica import validar_datos_tecnicos

VERSION_PROYECCION = "PRF04_1"


def proyectar(raw):
    resultado = ExtractionResult.model_validate(raw)
    item = resultado.item_proposal
    if resultado.status != "REQUIRES_REVIEW" or item is None or not item.name:
        return None
    pendientes = [
        {"codigo": w.code, "ruta": w.path, "mensaje": w.message}
        for w in resultado.warnings
        if w.severity != "INFO" and w.code not in {"MISSING_UNIT", "MISSING_AXIS"}
    ]
    generales = {}
    conflictivos = set()

    def registrar(destino, campo, valor, ambito):
        clave = (ambito, campo)
        if clave in conflictivos:
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
    dimensiones = {}
    ejes_conflictivos = set()
    for medida in item.dimensions:
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
            pendientes.append(
                {
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
            )
    for candidato in resultado.candidates:
        if candidato.candidate_id in item.unresolved and candidato.label == "DIMENSION":
            pendientes.append(
                {
                    "codigo": "MISSING_AXIS",
                    "ruta": "dimensiones",
                    "mensaje": f"Indique ejes y unidades de {candidato.text}.",
                    "resolucion": {"tipo": "DIMENSIONES_NUEVAS", "cantidad": 2},
                }
            )
    if dimensiones:
        generales["dimensiones"] = dimensiones
    for medida in item.thicknesses:
        destino = componentes.get(medida.component_ref) if medida.component_ref else generales
        if destino is not None and medida.unit:
            registrar(
                destino,
                "espesor",
                f"{medida.value} {medida.unit}",
                medida.component_ref or "general",
            )
    for color in (item.primary_color, item.secondary_color):
        if color:
            destino = componentes.get(color.component_ref) if color.component_ref else generales
            if destino is not None:
                registrar(destino, "color", color.value, color.component_ref or "general")
    # El contrato v1 admite relaciones explícitas a través de candidatos tipados.
    for candidato in resultado.candidates:
        if candidato.decision != "ACCEPTED":
            continue
        destino = componentes.get(candidato.component_ref) if candidato.component_ref else generales
        if destino is None:
            continue
        if candidato.label in {"MATERIAL", "COLOR", "ACABADO"}:
            registrar(
                destino,
                candidato.label.lower(),
                candidato.text,
                candidato.component_ref or "general",
            )
        if candidato.label == "CANTIDAD_INTERNA" and candidato.component_ref:
            valor = candidato.normalized_value
            if type(valor) is int and valor > 0:
                destino["cantidad_interna"] = valor
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
    grupos_usados = {c.get("conjunto_uid") for c in componentes.values()}
    datos = {
        "caracteristicas_generales": generales,
        "conjuntos": [g for g in grupos.values() if g["uid"] in grupos_usados],
        "componentes": list(componentes.values()),
        "accesorios": [
            f"{a.quantity} {a.name}" if a.quantity else a.name
            for a in item.accessories
            if not a.component_ref
        ],
        "descripcion_original": resultado.text_original,
    }
    validar_datos_tecnicos(datos)
    termino = normalizar(item.furniture_type_candidate or item.name)
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
    if precio and precio.mode == "TOTAL_NEGOCIADO":
        pendientes.append(
            {
                "codigo": "TOTAL_NEGOCIADO",
                "ruta": "comercial.precio_unitario",
                "mensaje": (
                    f"Se dictó un total de {precio.line_total} {precio.currency}; "
                    "indique el precio unitario."
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
