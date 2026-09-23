from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone
from homex_nlp.field_comparison import compare_fields
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from apps.capturas.models import Captura, EvaluacionNLP, ItemHumano, ItemIA
from apps.catalogo.models import ValorCatalogo
from apps.proformas.models import DetalleProforma, EspecificacionMueble, Proforma


class ConfirmacionHITLExistente(APIException):
    status_code = 409
    default_code = "captura_ya_confirmada"
    default_detail = "La captura ya fue incorporada mediante una corrección final."


@dataclass(frozen=True, slots=True)
class ConfirmacionHITL:
    captura: Captura
    detalle: DetalleProforma
    item_humano: ItemHumano
    evaluacion: EvaluacionNLP


def _valor_activo(*, concepto: str, valor_id: int, campo: str) -> ValorCatalogo:
    try:
        return ValorCatalogo.objects.select_related("concepto").get(
            pk=valor_id, concepto__codigo=concepto, activo=True
        )
    except ValorCatalogo.DoesNotExist as exc:
        raise ValidationError({campo: f"No pertenece a {concepto} activo."}) from exc


def _presente(valor: Any) -> bool:
    return valor is not None and valor != "" and valor != [] and valor != {}


def _datos_comparables(item) -> dict[str, Any]:
    datos = {
        "nombre": item.nombre,
        "espesor": item.espesor,
        "color_principal": item.color_principal,
        "color_secundario": item.color_secundario,
        "dimensiones": item.dimensiones,
        "accesorios": item.accesorios,
        "cantidad": item.cantidad,
        "precio_total": str(item.precio_total) if item.precio_total is not None else None,
        "observaciones": item.observaciones,
    }
    return {clave: valor for clave, valor in datos.items() if _presente(valor)}


def _crear_detalle(*, proforma, corregido, linea) -> DetalleProforma:
    tipo_item = _valor_activo(
        concepto="TIPO_ITEM", valor_id=linea["tipo_item_id"], campo="tipo_item_id"
    )
    if tipo_item.codigo != "MUEBLE_MEDIDA":
        raise ValidationError({"tipo_item_id": "HITL v1 sólo incorpora MUEBLE_MEDIDA."})
    unidad = _valor_activo(concepto="UNIDAD_MEDIDA", valor_id=linea["unidad_id"], campo="unidad_id")
    if unidad.codigo != "PIEZA":
        raise ValidationError({"unidad_id": "MUEBLE_MEDIDA se incorpora en PIEZA."})
    modo = linea["modo_calculo"]
    importe = linea.get("importe_negociado")
    precio = linea.get("precio_unitario")
    if modo == "PRECIO_UNITARIO":
        if precio is None:
            raise ValidationError({"precio_unitario": "Es obligatorio en PRECIO_UNITARIO."})
        if importe is not None:
            raise ValidationError({"importe_negociado": "No se admite en PRECIO_UNITARIO."})
    elif modo == "TOTAL_NEGOCIADO":
        if importe is None:
            raise ValidationError({"importe_negociado": "Es obligatorio en TOTAL_NEGOCIADO."})
        if precio is not None:
            raise ValidationError(
                {"precio_unitario": "En TOTAL_NEGOCIADO el unitario es derivado."}
            )
        precio = (importe / corregido["cantidad"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        raise ValidationError({"modo_calculo": "Modo de cálculo no admitido."})

    return DetalleProforma.objects.create(
        proforma=proforma,
        tipo_item=tipo_item,
        nombre=corregido["nombre"],
        descripcion=linea.get("descripcion"),
        cantidad=corregido["cantidad"],
        unidad=unidad,
        modo_calculo=modo,
        precio_unitario=precio,
        importe_negociado=importe,
        descuento=Decimal("0.00"),
    )


@transaction.atomic
def confirmar_captura(
    *,
    captura_id: int,
    intento_id: int,
    item_ia_id: int,
    item_corregido: dict,
    linea_comercial: dict,
    actor,
) -> ConfirmacionHITL:
    try:
        referencia = Captura.objects.only("proforma_id").get(pk=captura_id)
    except Captura.DoesNotExist as exc:
        raise ValidationError({"captura": "La captura no existe."}) from exc

    proforma = (
        Proforma.objects.select_for_update().select_related("estado").get(pk=referencia.proforma_id)
    )
    captura = Captura.objects.select_for_update().select_related("proforma").get(pk=captura_id)
    if captura.vendedor_id != actor.id and not (actor.is_staff or actor.is_superuser):
        raise PermissionDenied("No puede confirmar una captura de otro vendedor.")
    if proforma.estado.codigo == "APROBADA":
        raise ValidationError({"proforma": "Una proforma aprobada no admite confirmaciones HITL."})
    if captura.proforma_detalle_id is not None:
        raise ConfirmacionHITLExistente()
    if captura.estado != "COMPLETADA":
        raise ValidationError({"captura": "La captura todavía no terminó su procesamiento."})

    try:
        item_ia = (
            ItemIA.objects.select_for_update()
            .select_related("intento__captura")
            .get(pk=item_ia_id, intento_id=intento_id, intento__captura_id=captura_id)
        )
    except ItemIA.DoesNotExist as exc:
        raise ValidationError(
            {"item_ia_id": "El ítem IA no corresponde al intento y captura indicados."}
        ) from exc
    if item_ia.intento.estado != "FINALIZADO":
        raise ValidationError({"intento_id": "El intento no está FINALIZADO."})
    ultimo_finalizado = (
        captura.intentocaptura_set.filter(estado="FINALIZADO")
        .order_by("-numero_intento")
        .values_list("id", flat=True)
        .first()
    )
    if ultimo_finalizado != intento_id:
        raise ValidationError({"intento_id": "Existe un resultado finalizado más reciente."})
    if ItemHumano.objects.filter(item_ia=item_ia).exists():
        raise ConfirmacionHITLExistente()

    detalle = _crear_detalle(proforma=proforma, corregido=item_corregido, linea=linea_comercial)
    detalle.refresh_from_db()
    item_humano = ItemHumano.objects.create(
        item_ia=item_ia,
        nombre=item_corregido["nombre"],
        espesor=item_corregido.get("espesor"),
        color_principal=item_corregido.get("color_principal"),
        color_secundario=item_corregido.get("color_secundario"),
        dimensiones=item_corregido.get("dimensiones"),
        accesorios=item_corregido.get("accesorios"),
        cantidad=item_corregido["cantidad"],
        precio_total=detalle.total,
        observaciones=item_corregido.get("observaciones"),
        revisor=actor,
        revisado_at=timezone.now(),
        created_by=actor,
        updated_by=actor,
    )
    comparacion = compare_fields(_datos_comparables(item_ia), _datos_comparables(item_humano))
    precision_campo = (
        Decimal(comparacion.field_precision) if comparacion.field_precision is not None else None
    )
    precision_item = (
        (Decimal("1") if comparacion.item_equal else Decimal("0"))
        if comparacion.evaluable_fields
        else None
    )
    evaluacion = EvaluacionNLP.objects.create(
        item_humano=item_humano,
        version_metrica=comparacion.metric_version,
        fin_revision_at=item_humano.revisado_at,
        campos_totales=comparacion.evaluable_fields,
        campos_corregidos=comparacion.corrected_fields,
        campos_agregados=comparacion.added_fields,
        campos_eliminados=comparacion.removed_fields,
        precision_item=precision_item,
        precision_campo=precision_campo,
        evaluated_by=actor,
    )
    tipo_mueble = None
    if linea_comercial.get("tipo_mueble_id") is not None:
        tipo_mueble = _valor_activo(
            concepto="TIPO_MUEBLE",
            valor_id=linea_comercial["tipo_mueble_id"],
            campo="tipo_mueble_id",
        )
    EspecificacionMueble.objects.create(
        proforma_detalle=detalle,
        tipo_mueble=tipo_mueble,
        schema_version=1,
        espesor=item_humano.espesor,
        color_principal=item_humano.color_principal,
        color_secundario=item_humano.color_secundario,
        dimensiones=item_humano.dimensiones,
        accesorios=item_humano.accesorios,
        observaciones=item_humano.observaciones,
    )
    captura.proforma_detalle = detalle
    captura.updated_by = actor
    captura.save(update_fields=["proforma_detalle", "updated_by"])
    return ConfirmacionHITL(captura, detalle, item_humano, evaluacion)
