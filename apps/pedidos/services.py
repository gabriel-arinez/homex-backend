from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.pedidos.models import Pedido
from apps.proformas.services import _proforma_bloqueada, valor_catalogo


@transaction.atomic
def aprobar_proforma(*, proforma_id, actor):
    proforma = _proforma_bloqueada(proforma_id, actor)
    if proforma.estado.codigo != "ENVIADA":
        raise ValidationError({"estado": "Sólo una proforma ENVIADA puede aprobarse."})
    proforma.estado = valor_catalogo("ESTADO_PROFORMA", "APROBADA")
    proforma.updated_by = actor
    proforma.save(update_fields=["estado", "updated_by"])
    return Pedido.objects.select_related("proforma", "estado").get(proforma=proforma)


@transaction.atomic
def cancelar_pedido(*, pedido_id, actor):
    pedido = Pedido.objects.select_for_update().select_related("proforma").get(pk=pedido_id)
    if pedido.proforma.vendedor_id != actor.id and not (actor.is_staff or actor.is_superuser):
        raise ValidationError({"pedido": "No puede cancelar un pedido ajeno."})
    if pedido.estado.codigo == "CANCELADO":
        raise ValidationError({"estado": "El pedido ya está cancelado."})
    pedido.estado = valor_catalogo("ESTADO_PEDIDO", "CANCELADO")
    pedido.updated_by = actor
    pedido.save(update_fields=["estado", "updated_by"])
    pedido.refresh_from_db()
    return pedido
