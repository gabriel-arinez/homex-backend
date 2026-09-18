from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.proformas.models import DetalleProforma, Proforma


def recalculate_detalle(detalle: DetalleProforma) -> DetalleProforma:
    if detalle.modo_calculo == DetalleProforma.CalculationMode.NEGOTIATED:
        if detalle.monto_negociado is None:
            raise ValidationError("TOTAL_NEGOCIADO requiere importe negociado")
        detalle.total = detalle.monto_negociado
    else:
        detalle.total = detalle.cantidad * detalle.precio_unitario - detalle.descuento
    if detalle.total < Decimal(0):
        raise ValidationError("El total de línea no puede ser negativo")
    return detalle


@transaction.atomic
def recalcular_proforma(proforma_id: int) -> Proforma:
    proforma = Proforma.objects.select_for_update().get(pk=proforma_id)
    subtotal = Decimal(0)
    descuento = Decimal(0)
    for detalle in proforma.detalles.select_for_update():
        recalculate_detalle(detalle)
        detalle.save(update_fields=("total",))
        subtotal += detalle.total
        descuento += detalle.descuento
    proforma.subtotal, proforma.descuento_total, proforma.total = (
        subtotal + descuento,
        descuento,
        subtotal,
    )
    proforma.save(update_fields=("subtotal", "descuento_total", "total"))
    return proforma


def enviar_proforma(proforma_id: int, actor_id: int) -> Proforma:
    proforma = Proforma.objects.select_for_update().select_related("cliente").get(pk=proforma_id)
    if proforma.vendedor_id != actor_id:
        raise ValidationError("Solo el vendedor responsable puede enviar la proforma")
    if proforma.cliente_id is None:
        raise ValidationError("Una proforma enviada requiere cliente registrado")
    if proforma.estado.codigo != "BORRADOR":
        raise ValidationError("Solo un borrador puede enviarse")
    cliente = proforma.cliente
    proforma.cliente_nombre_snapshot = " ".join(
        filter(None, (cliente.nombres, cliente.apellidos))
    )
    proforma.cliente_empresa_snapshot = cliente.empresa
    proforma.cliente_celular_snapshot = cliente.celular
    proforma.cliente_direccion_snapshot = cliente.direccion
    proforma.estado = proforma.estado.__class__.objects.get(codigo="ENVIADA")
    proforma.actualizado_por_id = actor_id
    proforma.save()
    return proforma


def update_draft(proforma_id: int, actor_id: int, **changes) -> Proforma:
    proforma = Proforma.objects.select_for_update().get(pk=proforma_id)
    if proforma.vendedor_id != actor_id or proforma.estado.codigo != "BORRADOR":
        raise ValidationError("Solo el vendedor puede editar su borrador")
    protected = {
        "subtotal",
        "descuento_total",
        "total",
        "cliente_nombre_snapshot",
        "cliente_empresa_snapshot",
        "cliente_celular_snapshot",
        "cliente_direccion_snapshot",
    }
    if protected.intersection(changes):
        raise ValidationError("Los totales y snapshots no se editan directamente")
    for field, value in changes.items():
        setattr(proforma, field, value)
    proforma.actualizado_por_id = actor_id
    proforma.save()
    return proforma
