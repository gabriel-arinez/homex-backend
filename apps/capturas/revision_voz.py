"""Validate review claims against immutable server captures and append history."""

import json
from copy import deepcopy
from decimal import Decimal, InvalidOperation

from rest_framework.exceptions import ValidationError

from apps.capturas.limites import origen_canonico
from apps.capturas.models import Captura


def _error(message):
    raise ValidationError({"revision_humana_voz": message})


def _same(a, b):
    if isinstance(a, (dict, list)) or isinstance(b, (dict, list)):
        return a == b
    if a is None or b is None or isinstance(a, bool) or isinstance(b, bool):
        return a == b
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except (InvalidOperation, ValueError):
        return a == b


def _positive(value):
    try:
        return Decimal(str(value)).is_finite() and Decimal(str(value)) > 0
    except InvalidOperation:
        return False


def _value(data, field):
    if field.startswith("componentes."):
        _, uid, key = field.split(".", 2)
        component = next((c for c in data.get("componentes", []) if c.get("uid") == uid), {})
        return component.get(key)
    general = data.get("caracteristicas_generales") or {}
    dimensions = general.get("dimensiones", data.get("dimensiones", {}))
    if field.startswith("dimensiones."):
        return dimensions.get(field.split(".", 1)[1])
    if field in {"ancho", "alto", "largo", "profundidad", "diametro"}:
        return dimensions.get(field)
    if field == "dimensiones":
        return dimensions
    if field in data:
        return data[field]
    if "." in field:
        value = data
        for key in field.split("."):
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        return value
    from apps.catalogo.atributos_mueble import normalizar

    return next(
        (
            a.get("valor")
            for a in general.get("atributos", [])
            if normalizar(str(a.get("codigo") or a.get("nombre", ""))) == normalizar(field)
        ),
        None,
    )


def _pending_field(pending, final):
    resolution = pending.get("resolucion") or {}
    kind = resolution.get("tipo")
    if kind in {"DIMENSION", "ATRIBUTO_GENERAL"}:
        return resolution.get("clave")
    if kind == "COMPONENTE":
        return f"componentes.{resolution.get('uid')}.{resolution.get('campo')}"
    if kind == "DIMENSIONES_NUEVAS":
        return "dimensiones"
    if kind == "ESPESOR_SIN_COMPONENTE":
        # A human selects the actual destination; it must exist in the saved ficha.
        if final.startswith("componentes.") and final.endswith(".espesor"):
            return final
        return None
    return {
        "NO_QUANTITY": "cantidad",
        "INVALID_QUANTITY": "cantidad",
        "INVALID_PRICE": "precio_unitario",
        "TOTAL_NEGOCIADO": "precio_unitario",
        "TIPO_NO_RESUELTO": "tipo_mueble",
    }.get(pending.get("codigo"), pending.get("ruta") or pending.get("codigo"))


def validar_revision_voz(
    *,
    incoming,
    previous,
    actor,
    mode,
    final,
    detalle=None,
    session=None,
    category=None,
    product_id=None,
):
    """Existing server history is never replaced by a browser snapshot.

    The caller owns its destination's row lock and enclosing transaction. New
    capture claims also lock the capture, preventing cross-destination races.
    """
    previous = deepcopy(previous or [])
    if not isinstance(incoming, list) or len(incoming) > 200:
        _error("La revisión debe ser una lista acotada.")
    result = previous
    known_snapshots = {json.dumps(item, sort_keys=True, ensure_ascii=False) for item in previous}
    known_decisions = {
        event["decision_id"]: (snapshot["captura_asistida_id"], event)
        for snapshot in previous
        for event in snapshot.get("decisiones", [])
        if isinstance(event, dict) and "decision_id" in event
    }
    latest_new = {}
    for item in incoming:
        if isinstance(item, dict) and isinstance(item.get("decisiones", []), list):
            for event in item.get("decisiones", []):
                if (
                    isinstance(event, dict)
                    and isinstance(event.get("decision_id"), str)
                    and event["decision_id"] not in known_decisions
                ):
                    key = (
                        item.get("captura_asistida_id"),
                        event.get("review_id"),
                        event.get("field"),
                    )
                    if all(isinstance(value, (int, str)) for value in key):
                        latest_new[key] = event["decision_id"]
    for snapshot in incoming:
        if not isinstance(snapshot, dict):
            _error("Cada revisión debe ser un objeto.")
        serialized = json.dumps(snapshot, sort_keys=True, ensure_ascii=False)
        if serialized in known_snapshots:
            continue
        if set(snapshot) - {
            "captura_asistida_id",
            "pendientes_originales",
            "asignaciones_espesor",
            "descartes",
            "decisiones",
            "intento_id",
            "captura_origen",
        }:
            _error("La revisión contiene campos no admitidos.")
        capture_id = snapshot.get("captura_asistida_id")
        if not isinstance(capture_id, int) or isinstance(capture_id, bool):
            _error("Identificador de interpretación inválido.")
        capture = (
            Captura.objects.select_for_update()
            .filter(pk=capture_id, vendedor=actor, modo_captura=mode)
            .first()
        )
        if not capture:
            _error("Interpretación no disponible para este actor.")
        if product_id:
            from apps.catalogo.models import Producto

            if (
                Producto.objects.exclude(pk=product_id)
                .filter(revision_humana_voz__contains=[{"captura_asistida_id": capture_id}])
                .exists()
            ):
                _error("La interpretación pertenece a otro producto.")
        if category and capture.categoria_catalogo != category:
            _error("La categoría no corresponde a la interpretación.")
        if detalle:
            if capture.proforma_id not in {
                None,
                detalle.proforma_id,
            } or capture.proforma_detalle_id not in {None, detalle.pk}:
                _error("La interpretación pertenece a otra ficha.")
            if capture.proforma_detalle_id is None and (
                not session or str(capture.sesion_borrador) != str(session)
            ):
                _error("La sesión no corresponde a la interpretación.")
            if capture.moneda_contexto_codigo != detalle.proforma.moneda.codigo:
                _error("Moneda incompatible con la interpretación.")

        # Validate every ancestor's owner/context, including the original ASR.
        # Linking a finished ficha sets only the leaf's proforma, so compare the
        # immutable capture context without the subsequently assigned linkage.
        def validate_origin(origin):
            if (
                origin.vendedor_id != actor.pk
                or origin.modo_captura != mode
                or origin.sesion_borrador != capture.sesion_borrador
            ):
                _error("Origen de interpretación incompatible.")

        if capture.captura_origen_id:
            origin = capture.captura_origen
            validate_origin(origin)
            origen_canonico(origin, validar=validate_origin)
        attempt = capture.intentocaptura_set.order_by("-numero_intento").first()
        if capture.estado != "COMPLETADA" or not attempt or attempt.estado != "FINALIZADO":
            _error("La interpretación no está completada.")
        raw = attempt.resultado_raw or {}
        projection = attempt.proyeccion_configurador or {}
        if mode == "ASISTIDA_CREACION_MUEBLE":
            if raw.get("status") != "REQUIRES_REVIEW" or not projection:
                _error("La captura no tiene una propuesta revisable.")
            from apps.capturas.api.proyeccion_serializers import PendienteAsistidaSerializer

            pending = list(
                PendienteAsistidaSerializer(projection.get("pendientes", []), many=True).data
            )
            if snapshot.get("pendientes_originales", pending) != pending:
                _error("Los pendientes no coinciden con la interpretación original.")
            original = deepcopy(projection.get("especificacion", {}).get("datos_tecnicos") or {})
            original.update(projection.get("comercial", {}))
            original["tipo_mueble"] = projection.get("especificacion", {}).get("tipo_mueble")
            reviews = {f"pending:{i}": p for i, p in enumerate(pending)}
        else:
            if not raw.get("fields"):
                _error("La captura no tiene una propuesta revisable.")
            pending = []
            original = raw["fields"]
            reviews = {r["review_id"]: r for r in raw.get("field_reviews", [])}
            catalog_fields = set(raw["fields"]) | {
                e["label"] for e in raw.get("evidence", []) if e.get("decision") == "ACCEPTED"
            }
            for field in catalog_fields:
                reviews[f"field:{field}"] = {
                    "field": field,
                    "evidence_ids": [
                        e["candidate_id"]
                        for e in raw.get("evidence", [])
                        if e["label"] == field and e["decision"] == "ACCEPTED"
                    ],
                }
            if (
                snapshot.get("pendientes_originales", [])
                or snapshot.get("asignaciones_espesor", [])
                or snapshot.get("descartes", [])
            ):
                _error("Resolución incompatible con el catálogo.")
        clean = deepcopy(snapshot)
        source = capture.captura_origen if capture.captura_origen_id else capture
        root_id = origen_canonico(source).pk
        if (
            snapshot.get("intento_id", attempt.pk) != attempt.pk
            or snapshot.get("captura_origen", root_id) != root_id
        ):
            _error("La ejecución o el origen no corresponde a la interpretación.")
        clean["intento_id"] = attempt.pk
        clean["captura_origen"] = root_id
        if mode == "ASISTIDA_CREACION_MUEBLE":
            clean["pendientes_originales"] = deepcopy(pending)
        for key in ("asignaciones_espesor", "descartes", "decisiones"):
            if key in clean and (not isinstance(clean[key], list) or len(clean[key]) > 200):
                _error("Las decisiones deben ser una lista acotada.")
        for kind in ("asignaciones_espesor", "descartes"):
            for action in clean.get(kind, []):
                if not isinstance(action, dict) or not isinstance(action.get("indice"), int):
                    _error("Resolución de pendiente inválida.")
                index = action["indice"]
                if (
                    index < 0
                    or index >= len(pending)
                    or action.get("pendiente_original") != pending[index]
                ):
                    _error("La evidencia del pendiente no corresponde.")
                if kind == "descartes":
                    if pending[index].get("codigo") in {
                        "NO_QUANTITY",
                        "INVALID_QUANTITY",
                        "INVALID_PRICE",
                        "TIPO_NO_RESUELTO",
                    }:
                        _error("Un dato comercial obligatorio debe corregirse, no descartarse.")
                    if (
                        not isinstance(action.get("motivo"), str)
                        or not action["motivo"].strip()
                        or action.get("accion_humana") != "descartado"
                    ):
                        _error("El descarte requiere una acción y un motivo explícitos.")
                else:
                    if (pending[index].get("resolucion") or {}).get(
                        "tipo"
                    ) != "ESPESOR_SIN_COMPONENTE":
                        _error("La asignación no corresponde a un espesor pendiente.")
                    if not _value(final, f"componentes.{action.get('componente_uid')}.espesor"):
                        _error("El componente resuelto debe contener un espesor válido.")
        fresh = []
        for event in clean.get("decisiones", []):
            required = {
                "decision_id",
                "review_id",
                "field",
                "evidence_ids",
                "estado",
                "valor_original",
                "valor_final",
            }
            if (
                not isinstance(event, dict)
                or not required <= event.keys()
                or event.keys() - required - {"motivo"}
            ):
                _error("Estructura de decisión inválida.")
            if (
                not all(
                    isinstance(event.get(k), str) and event[k]
                    for k in ("decision_id", "review_id", "field")
                )
                or len(event["decision_id"]) > 20000
            ):
                _error("Identidad de decisión inválida.")
            existing = known_decisions.get(event["decision_id"])
            if existing is not None:
                if existing != (capture_id, event):
                    _error("Una decisión histórica no puede modificarse.")
                continue
            if (
                mode == "ASISTIDA_CREACION_MUEBLE"
                and event["review_id"] == f"field:{event['field']}"
            ):
                if _value(original, event["field"]) is None:
                    _error("El campo sugerido no pertenece a la propuesta.")
                reviews[event["review_id"]] = {"generic_field": event["field"]}
            review = reviews.get(event["review_id"])
            if review is None:
                _error("La observación no pertenece a la interpretación.")
            expected_field = (
                review.get("generic_field") or _pending_field(review, event["field"])
                if mode == "ASISTIDA_CREACION_MUEBLE"
                else review["field"]
            )
            if event["field"] != expected_field:
                _error("El campo no corresponde a la observación.")
            evidence = (
                [e["evidence_id"] for e in review.get("evidencias", [])]
                if mode == "ASISTIDA_CREACION_MUEBLE"
                else review.get("evidence_ids", [])
            )
            if not isinstance(event["evidence_ids"], list) or not all(
                isinstance(value, str) for value in event["evidence_ids"]
            ):
                _error("Los identificadores de evidencia deben ser texto.")
            if set(event["evidence_ids"]) != set(evidence):
                _error("Las evidencias no corresponden a la observación.")
            original_value = (
                (review.get("resolucion") or {}).get("valor")
                if (review.get("resolucion") or {}).get("tipo") == "ESPESOR_SIN_COMPONENTE"
                else _value(original, event["field"])
            )
            if not _same(event["valor_original"], original_value):
                _error("El valor original no corresponde a la propuesta.")
            state = event["estado"]
            if state not in {"confirmado", "corregido", "descartado"}:
                _error("Estado de decisión inválido.")
            if state == "descartado":
                if not isinstance(event.get("motivo"), str) or not event["motivo"].strip():
                    _error("El descarte requiere un motivo explícito.")
                if mode == "ASISTIDA_CREACION_MUEBLE" and review.get("codigo") in {
                    "NO_QUANTITY",
                    "INVALID_QUANTITY",
                    "INVALID_PRICE",
                    "TIPO_NO_RESUELTO",
                }:
                    _error("Un dato comercial obligatorio debe corregirse, no descartarse.")
            else:
                actual = _value(final, event["field"])
                latest = (
                    latest_new.get((capture_id, event["review_id"], event["field"]))
                    == event["decision_id"]
                )
                if latest and (
                    actual is None or actual == "" or not _same(event["valor_final"], actual)
                ):
                    _error("La decisión no corresponde al valor guardado.")
                actual = event["valor_final"]
                if event["field"] in {"cantidad", "precio_unitario", "precio_lista"}:
                    catalog_price = mode == "CATALOGO_CREACION" and event["field"] == "precio_lista"
                    try:
                        number = Decimal(str(actual))
                        valid = number.is_finite() and (
                            number >= 0 if catalog_price else number > 0
                        )
                    except InvalidOperation:
                        valid = False
                    if not valid:
                        if catalog_price:
                            _error("El precio no puede ser negativo.")
                        _error("El valor comercial confirmado debe ser positivo.")
                if (
                    event["field"].startswith("dimensiones.")
                    or event["field"] == "dimensiones"
                    or (review.get("resolucion") or {}).get("tipo")
                    in {
                        "DIMENSION",
                        "DIMENSIONES_NUEVAS",
                    }
                ):
                    if not isinstance(actual, dict):
                        _error("La resolución de medida debe ser un objeto.")
                    values = [actual] if "valor" in actual else list(actual.values())
                    if not values or any(
                        not isinstance(value, dict)
                        or value.get("unidad") not in {"mm", "cm", "m"}
                        or not _positive(value.get("valor"))
                        for value in values
                    ):
                        _error("La medida resuelta requiere valor positivo y unidad válida.")
                if state == "confirmado" and not _same(
                    event["valor_original"], event["valor_final"]
                ):
                    _error("Confirmar no puede modificar el valor original.")
            known_decisions[event["decision_id"]] = (capture_id, event)
            fresh.append(event)
        if "decisiones" in clean:
            clean["decisiones"] = fresh
        # A new snapshot with no new events is only meaningful for a new legacy
        # thickness/discard resolution; compare it without its events as well.
        comparable = {
            k: v
            for k, v in clean.items()
            if k not in {"decisiones", "intento_id", "captura_origen"}
        }
        same_legacy = any(
            {
                k: v
                for k, v in old.items()
                if k not in {"decisiones", "intento_id", "captura_origen"}
            }
            == comparable
            for old in result
        )
        if same_legacy and not fresh:
            continue
        result.append(clean)
        known_snapshots.add(json.dumps(clean, sort_keys=True, ensure_ascii=False))
    return result
