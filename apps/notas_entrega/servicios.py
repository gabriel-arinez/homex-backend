from django.core.exceptions import ValidationError
from django.db import transaction

from apps.documentos.numeracion import siguiente_numero_comercial
from apps.notas_entrega.models import NotaEntrega
from apps.pedidos.models import Pedido


@transaction.atomic
def emitir_nota_entrega(*, pedido_id: int, vendedor_id: int, actor_id: int) -> NotaEntrega:
    """Emite la única nota de entrega cuando el pedido está listo para entregar."""
    pedido = Pedido.objects.select_for_update().select_related("estado").get(pk=pedido_id)
    if pedido.estado.codigo != "LISTO_ENTREGA":
        raise ValidationError("La nota sólo puede emitirse para un pedido listo para entrega")
    if NotaEntrega.objects.filter(pedido=pedido).exists():
        raise ValidationError("El pedido ya tiene una nota de entrega")
    return NotaEntrega.objects.create(
        pedido=pedido,
        vendedor_id=vendedor_id,
        numero=siguiente_numero_comercial(
            sequence_nombre="seq_notas_entrega_numero", modelo=NotaEntrega
        ),
        creado_por_id=actor_id,
        actualizado_por_id=actor_id,
    )
