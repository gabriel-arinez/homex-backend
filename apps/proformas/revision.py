"""Huella optimista del agregado comercial AP3.

Incluye los datos persistidos de cabecera, líneas y fichas técnicas. Al
calcularla bajo el bloqueo de proforma durante PUT se detectan modificaciones
intermedias de otros editores y del flujo NLP/HITL sin alterar las tablas.
"""

import hashlib
import json

from apps.proformas.models import DetalleProforma, EspecificacionMueble, Proforma


def revision_proforma(proforma: Proforma) -> str:
    cabecera = Proforma.objects.filter(pk=proforma.pk).values().get()
    detalles = list(DetalleProforma.objects.filter(proforma_id=proforma.pk).order_by("id").values())
    especificaciones = list(
        EspecificacionMueble.objects.filter(proforma_detalle__proforma_id=proforma.pk)
        .order_by("proforma_detalle_id")
        .values()
    )
    representacion = json.dumps(
        [cabecera, detalles, especificaciones],
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        ensure_ascii=False,
    )
    return hashlib.sha256(representacion.encode("utf-8")).hexdigest()
