from django.utils.html import escape

from apps.notas_entrega.models import NotaEntrega
from apps.ordenes_trabajo.models import OrdenTrabajo
from apps.proformas.models import Proforma
from apps.recibos.models import Recibo


def _html(titulo, filas):
    contenido = "".join(
        f"<li><strong>{escape(str(clave))}</strong>: {escape(str(valor))}</li>"
        for clave, valor in filas
    )
    return f"<article><h1>{escape(titulo)}</h1><ul>{contenido}</ul></article>"


def renderizar_proforma(proforma_id):
    proforma = Proforma.objects.prefetch_related("detalles").get(pk=proforma_id)
    return _html(
        f"Proforma #{proforma.numero}",
        [("total", proforma.total), *[(d.nombre, d.total) for d in proforma.detalles.all()]],
    )


def renderizar_orden_trabajo(orden_trabajo_id):
    orden = OrdenTrabajo.objects.select_related("pedido__proforma").get(pk=orden_trabajo_id)
    return _html(
        f"Orden de trabajo #{orden.numero}",
        [("pedido", orden.pedido_id), ("proforma", orden.pedido.proforma.numero)],
    )


def renderizar_recibo(recibo_id):
    recibo = Recibo.objects.select_related("pedido", "tipo_pago").get(pk=recibo_id)
    return _html(
        f"Recibo #{recibo.numero}",
        [("pedido", recibo.pedido_id), ("pago", recibo.pago_actual), ("estado", recibo.estado)],
    )


def renderizar_nota_entrega(nota_entrega_id):
    nota = NotaEntrega.objects.select_related("pedido").get(pk=nota_entrega_id)
    return _html(
        f"Nota de entrega #{nota.numero}",
        [("pedido", nota.pedido_id), ("fecha_emision", nota.fecha)],
    )
