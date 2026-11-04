import json

from django.db import transaction
from django.utils.html import escape
from rest_framework.exceptions import ValidationError

from apps.core.permissions import es_jefe_taller
from apps.documentos.models import ArchivoAdjunto
from apps.media.storage import privado
from apps.notas_entrega.models import NotaEntrega
from apps.ordenes_trabajo.models import OrdenTrabajo
from apps.proformas.models import Proforma
from apps.proformas.services import _exigir_proforma_editable, _proforma_bloqueada
from apps.recibos.models import Recibo


def _html(titulo, filas):
    contenido = "".join(
        f"<li><strong>{escape(str(clave))}</strong>: {escape(str(valor))}</li>"
        for clave, valor in filas
    )
    return f"<article><h1>{escape(titulo)}</h1><ul>{contenido}</ul></article>"


def renderizar_proforma(proforma_id):
    proforma = Proforma.objects.prefetch_related(
        "detalles__tipo_item", "detalles__especificacionmueble"
    ).get(pk=proforma_id)
    filas = [("total", proforma.total)]
    for indice, detalle in enumerate(proforma.detalles.all(), start=1):
        filas.append((detalle.nombre, detalle.total))
        if detalle.tipo_item.codigo != "MUEBLE_MEDIDA":
            continue
        especificacion = getattr(detalle, "especificacionmueble", None)
        if especificacion is None:
            continue
        if detalle.descripcion:
            filas.append((f"Descripción del mueble {indice}", detalle.descripcion))
        filas.append(
            (
                f"Especificación del mueble {indice}",
                json.dumps(especificacion.datos_tecnicos, ensure_ascii=False),
            )
        )
    return _html(f"Proforma #{proforma.numero}", filas)


def renderizar_orden_trabajo(orden_trabajo_id, *, actor=None):
    orden = OrdenTrabajo.objects.select_related("pedido__proforma").get(pk=orden_trabajo_id)
    filas = [("Pedido", orden.pedido_id), ("Proforma", orden.pedido.proforma.numero)]
    for indice, detalle in enumerate(
        orden.pedido.proforma.detalles.select_related("tipo_item", "unidad").all(), start=1
    ):
        filas.append(
            (f"Ítem {indice}", f"{detalle.nombre} — {detalle.cantidad} {detalle.unidad.nombre}")
        )
        # La OT es única: catálogo siempre resumido, sin fichas ni precios.
        # La ficha de fabricación de muebles se reserva al rol de jefe de taller.
        if detalle.tipo_item.codigo != "MUEBLE_MEDIDA" or not es_jefe_taller(actor):
            continue
        especificacion = getattr(detalle, "especificacionmueble", None)
        if especificacion is None:
            continue
        if detalle.descripcion:
            filas.append((f"Descripción del mueble {indice}", detalle.descripcion))
        datos = dict(especificacion.datos_tecnicos)
        if especificacion.observaciones:
            datos["observaciones"] = especificacion.observaciones
        filas.append(
            (
                f"Ficha técnica del mueble {indice}",
                json.dumps(
                    {k: v for k, v in datos.items() if v not in (None, "", [], {})},
                    ensure_ascii=False,
                ),
            )
        )
    return _html(f"Orden de trabajo #{orden.numero}", filas)


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


@transaction.atomic
def adjuntar_imagen(*, proforma_id, detalle_id, archivo, actor) -> ArchivoAdjunto:
    proforma = _proforma_bloqueada(proforma_id, actor)
    _exigir_proforma_editable(proforma)
    detalle = proforma.detalles.filter(pk=detalle_id).first()
    if detalle is None:
        raise ValidationError({"detalle": "El detalle no pertenece a la proforma."})
    from apps.documentos.models import GaleriaBorrador
    from apps.media.gallery import subir

    galeria = GaleriaBorrador.objects.filter(detalle=detalle).first()
    qs = ArchivoAdjunto.objects.filter(proforma_detalle=detalle)

    def crear(**kw):
        mime, size = kw.pop("mime"), kw.pop("size")
        return ArchivoAdjunto.objects.create(
            **kw,
            galeria=galeria,
            proforma=proforma,
            proforma_detalle=detalle,
            nombre_storage=kw["ruta_storage"].split("/")[-1],
            mime_type=mime,
            tamano_bytes=size,
            privado=True,
            created_by=actor,
            updated_by=actor,
        )

    return subir(qs, archivo, crear, storage=privado(), prefijo="proformas/")


@transaction.atomic
def eliminar_adjunto(*, proforma_id, detalle_id, archivo_id, actor) -> None:
    proforma = _proforma_bloqueada(proforma_id, actor)
    _exigir_proforma_editable(proforma)
    adjunto = ArchivoAdjunto.objects.filter(
        pk=archivo_id, proforma=proforma, proforma_detalle_id=detalle_id
    ).first()
    if adjunto is None:
        raise ValidationError({"archivo": "El adjunto no pertenece al detalle indicado."})
    from apps.media.gallery import modificar

    modificar(
        ArchivoAdjunto.objects.filter(proforma=proforma, proforma_detalle_id=detalle_id),
        {"eliminar": adjunto.pk},
    )


def adjunto_publico(adjunto: ArchivoAdjunto) -> dict:
    return {
        "id": adjunto.id,
        "sha256": adjunto.sha256,
        "nombre": adjunto.nombre,
        "mime_type": adjunto.mime_type,
        "tamano_bytes": adjunto.tamano_bytes,
        "url": f"/api/v1/imagenes-privadas/{adjunto.pk}/",
        "posicion": adjunto.posicion,
        "principal": adjunto.principal,
        "dimensiones": adjunto.dimensiones,
        "variantes": {
            w: f"/api/v1/imagenes-privadas/{adjunto.pk}/?ancho={w}" for w in adjunto.variantes
        },
    }
