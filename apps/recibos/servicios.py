from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from apps.documentos.numeracion import siguiente_numero_comercial
from apps.pedidos.models import Pedido
from apps.recibos.models import Recibo


@transaction.atomic
def emitir_recibo(
    *,
    pedido_id: int,
    actor_id: int,
    nombre_completo: str,
    monto_literal: str,
    concepto: str,
    tipo_pago_id: int,
    pago_actual: Decimal,
    numero_cheque: str = "",
    banco: str = "",
) -> Recibo:
    """Registra un cobro sin permitir que los recibos emitidos superen el total."""
    pedido = (
        Pedido.objects.select_for_update().select_related("proforma", "estado").get(pk=pedido_id)
    )
    if pedido.estado.codigo == "CANCELADO":
        raise ValidationError("No se aceptan cobros en pedidos cancelarados")
    if pago_actual <= 0:
        raise ValidationError("El pago debe ser positivo")

    total = pedido.proforma.total
    paid = Recibo.objects.select_for_update().filter(
        pedido=pedido, estado=Recibo.Status.ISSUED
    ).aggregate(value=Sum("pago_actual"))["value"] or Decimal("0.00")
    a_cuenta = paid + pago_actual
    if a_cuenta > total:
        raise ValidationError("El pago supera el saldo pendiente del pedido")

    return Recibo.objects.create(
        numero=siguiente_numero_comercial(sequence_nombre="seq_recibos_numero", modelo=Recibo),
        pedido=pedido,
        nombre_completo=nombre_completo,
        monto_literal=monto_literal,
        concepto=concepto,
        tipo_pago_id=tipo_pago_id,
        numero_cheque=numero_cheque,
        banco=banco,
        total=total,
        pago_actual=pago_actual,
        a_cuenta=a_cuenta,
        saldo=total - a_cuenta,
        creado_por_id=actor_id,
        actualizado_por_id=actor_id,
    )


@transaction.atomic
def anular_recibo(*, recibo_id: int, actor_id: int) -> Recibo:
    """Anula un recibo erróneo sin borrar ni reescribir su comprobante histórico."""
    recibo = Recibo.objects.select_for_update().select_related("pedido").get(pk=recibo_id)
    Pedido.objects.select_for_update().get(pk=recibo.pedido_id)
    if recibo.estado != Recibo.Status.ISSUED:
        raise ValidationError("Sólo se pueden anular recibos emitidos")
    recibo.estado = Recibo.Status.VOIDED
    recibo.actualizado_por_id = actor_id
    recibo.save(update_fields=("estado", "actualizado_por"))
    return recibo
