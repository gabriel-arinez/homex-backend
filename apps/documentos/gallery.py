from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotFound, ValidationError

from apps.documentos.models import GaleriaBorrador
from apps.proformas.services import _exigir_proforma_editable, _proforma_bloqueada


def bloquear(galeria_id, actor, *, editar=False):
    referencia = get_object_or_404(
        GaleriaBorrador.objects.select_related("detalle__proforma"), pk=galeria_id
    )
    if (
        referencia.detalle_id
        and referencia.detalle.proforma.vendedor_id != actor.id
        and not (actor.is_staff or actor.is_superuser)
    ):
        raise NotFound()
    if referencia.detalle_id:
        _proforma_bloqueada(referencia.detalle.proforma_id, actor)
    galeria = get_object_or_404(GaleriaBorrador.objects.select_for_update(), pk=galeria_id)
    if galeria.detalle_id:
        proforma = _proforma_bloqueada(galeria.detalle.proforma_id, actor)
        if editar:
            _exigir_proforma_editable(proforma)
    elif galeria.propietario_id != actor.id:
        raise NotFound()
    return galeria


@transaction.atomic
def vincular(galeria_id, detalle, actor, sesion):
    galeria = bloquear(galeria_id, actor, editar=True)
    if detalle.tipo_item.codigo != "MUEBLE_MEDIDA":
        raise ValidationError({"galeria_id": "Sólo se admiten imágenes para muebles a pedido."})
    if galeria.detalle_id and galeria.detalle_id != detalle.id:
        raise ValidationError({"galeria_id": "La galería ya pertenece a otra línea."})
    if not galeria.detalle_id and str(galeria.sesion) != str(sesion):
        raise ValidationError({"galeria_id": "La galería pertenece a otro borrador."})
    galeria.detalle = detalle
    galeria.save(update_fields=["detalle", "actualizado"])
    galeria.imagenes.update(proforma=detalle.proforma, proforma_detalle=detalle)
