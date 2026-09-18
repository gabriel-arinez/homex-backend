from django.core.exceptions import ValidationError
from django.db import connection, transaction

from apps.catalogo.models import Producto, ValorCatalogo
from apps.documentos.numeracion import siguiente_numero_comercial
from apps.movimientos_stock.models import MovimientoStock
from apps.ordenes_trabajo.models import OrdenTrabajo
from apps.pedidos.models import Pedido, TransicionEstadoPedido
from apps.proformas.models import Proforma
from apps.recibos.models import Recibo


def value(codigo: str) -> ValorCatalogo:
    return ValorCatalogo.objects.get(codigo=codigo)


@transaction.atomic
def aprobar(proforma_id: int, actor_id: int) -> Pedido:
    """Aprueba una proforma enviada y registra todos sus efectos comerciales."""
    proforma = Proforma.objects.select_for_update().get(pk=proforma_id)
    if proforma.vendedor_id != actor_id or proforma.estado.codigo != "ENVIADA":
        raise ValidationError("La proforma no puede aprobarse")

    detalles = list(proforma.detalles.select_for_update().order_by("pk"))
    products = {
        producto.pk: producto
        for producto in Producto.objects.select_for_update()
        .filter(pk__in=[detalle.producto_id for detalle in detalles if detalle.producto_id])
        .order_by("pk")
    }
    for detalle in detalles:
        if detalle.producto_id and products[detalle.producto_id].stock < detalle.cantidad:
            raise ValidationError("Stock insuficiente")

    pedido = Pedido.objects.create(
        proforma=proforma,
        estado=value("CONFIRMADO"),
        creado_por_id=actor_id,
    )
    for detalle in detalles:
        if not detalle.producto_id:
            continue
        producto = products[detalle.producto_id]
        if connection.vendor != "postgresql":
            producto.stock -= detalle.cantidad
            producto.save(update_fields=("stock",))
        MovimientoStock.objects.create(
            producto=producto,
            tipo_movimiento=value("VENTA"),
            cantidad=-detalle.cantidad,
            pedido=pedido,
            creado_por_id=actor_id,
        )

    OrdenTrabajo.objects.create(
        pedido=pedido,
        numero=siguiente_numero_comercial(
            sequence_nombre="seq_ordenes_trabajo_numero", modelo=OrdenTrabajo
        ),
        estado=value("PENDIENTE"),
    )
    proforma.estado = value("APROBADA")
    proforma.actualizado_por_id = actor_id
    proforma.save(update_fields=("estado", "actualizado_por"))
    return pedido


@transaction.atomic
def transicionar_pedido(pedido_id: int, destino_codigo: str) -> Pedido:
    """Cambia un pedido sólo mediante una transición configurada explícitamente."""
    pedido = Pedido.objects.select_for_update().select_related("estado").get(pk=pedido_id)
    destino = value(destino_codigo)
    if not TransicionEstadoPedido.objects.filter(origen=pedido.estado, destino=destino).exists():
        raise ValidationError("Transición de pedido no permitida")
    pedido.estado = destino
    pedido.save(update_fields=("estado",))
    return pedido


@transaction.atomic
def cancelar(pedido_id: int, actor_id: int) -> Pedido:
    """Cancela un pedido sin cobros y revierte una sola vez cada venta de stock."""
    pedido = Pedido.objects.select_for_update().select_related("estado").get(pk=pedido_id)
    if Recibo.objects.filter(pedido=pedido, estado=Recibo.Status.ISSUED).exists():
        raise ValidationError("No se puede cancelarar un pedido con recibos emitidos")
    if pedido.estado.codigo not in {"CONFIRMADO", "EN_PRODUCCION", "LISTO_ENTREGA"}:
        raise ValidationError("Pedido no cancelarable")

    sales = list(
        MovimientoStock.objects.select_for_update()
        .filter(pedido=pedido, tipo_movimiento__codigo="VENTA")
        .order_by("pk")
    )
    for sale in sales:
        if MovimientoStock.objects.filter(referencia=sale).exists():
            raise ValidationError("Venta ya revertida")
        producto = Producto.objects.select_for_update().get(pk=sale.producto_id)
        if connection.vendor != "postgresql":
            producto.stock += -sale.cantidad
            producto.save(update_fields=("stock",))
        MovimientoStock.objects.create(
            producto=producto,
            tipo_movimiento=value("REVERSA_VENTA"),
            cantidad=-sale.cantidad,
            pedido=pedido,
            referencia=sale,
            creado_por_id=actor_id,
        )

    pedido.estado = value("CANCELADO")
    pedido.save(update_fields=("estado",))
    return pedido
