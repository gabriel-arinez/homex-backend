from django.template.loader import render_to_string

from apps.notas_entrega.models import NotaEntrega
from apps.ordenes_trabajo.models import OrdenTrabajo
from apps.proformas.models import Proforma
from apps.recibos.models import Recibo


def _proforma_context(proforma: Proforma) -> dict:
    return {
        "proforma": proforma,
        "cliente_nombre": proforma.cliente_nombre_snapshot,
        "cliente_empresa": proforma.cliente_empresa_snapshot,
        "cliente_celular": proforma.cliente_celular_snapshot,
        "cliente_direccion": proforma.cliente_direccion_snapshot,
        "detalles": proforma.detalles.all().order_by("pk"),
    }


def renderizar_proforma(proforma_id: int) -> str:
    proforma = Proforma.objects.prefetch_related("detalles").get(pk=proforma_id)
    return render_to_string("documentos/proforma.html", _proforma_context(proforma))


def renderizar_orden_trabajo(work_order_id: int) -> str:
    work_order = (
        OrdenTrabajo.objects.select_related("pedido__proforma")
        .prefetch_related("pedido__proforma__detalles")
        .get(pk=work_order_id)
    )
    context = _proforma_context(work_order.pedido.proforma) | {"orden_trabajo": work_order}
    return render_to_string("documentos/orden_trabajo.html", context)


def renderizar_nota_entrega(nota_entrega_id: int) -> str:
    nota_entrega = (
        NotaEntrega.objects.select_related("pedido__proforma", "vendedor")
        .prefetch_related("pedido__proforma__detalles")
        .get(pk=nota_entrega_id)
    )
    context = _proforma_context(nota_entrega.pedido.proforma) | {"nota_entrega": nota_entrega}
    return render_to_string("documentos/nota_entrega.html", context)


def renderizar_recibo(recibo_id: int) -> str:
    recibo = Recibo.objects.select_related("pedido__proforma", "tipo_pago").get(pk=recibo_id)
    return render_to_string("documentos/recibo.html", {"recibo": recibo})
