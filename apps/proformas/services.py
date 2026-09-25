from decimal import Decimal

from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.catalogo.models import Producto, ValorCatalogo
from apps.catalogo.services import precio_catalogo_vigente
from apps.core.exceptions import ConflictoComercial
from apps.proformas.models import DetalleProforma, EspecificacionMueble, Proforma


class ErrorComercial(ValidationError):
    pass


def valor_catalogo(concepto: str, codigo: str) -> ValorCatalogo:
    try:
        return ValorCatalogo.objects.get(concepto__codigo=concepto, codigo=codigo, activo=True)
    except ValorCatalogo.DoesNotExist as exc:
        raise ErrorComercial({"catalogo": f"No existe {concepto}.{codigo} activo."}) from exc


def _siguiente_numero_proforma() -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval('seq_proformas_numero')")
        return cursor.fetchone()[0]


@transaction.atomic
def crear_proforma(*, actor, moneda_codigo="BOB", **datos) -> Proforma:
    return Proforma.objects.create(
        numero=_siguiente_numero_proforma(),
        vendedor=actor,
        estado=valor_catalogo("ESTADO_PROFORMA", "BORRADOR"),
        moneda=valor_catalogo("MONEDA", moneda_codigo),
        fecha=timezone.localdate(),
        created_by=actor,
        updated_by=actor,
        **datos,
    )


def _proforma_bloqueada(proforma_id: int, actor) -> Proforma:
    try:
        proforma = Proforma.objects.select_for_update().get(pk=proforma_id)
    except Proforma.DoesNotExist as exc:
        raise ErrorComercial({"proforma": "La proforma no existe."}) from exc
    if proforma.vendedor_id != actor.id and not (actor.is_staff or actor.is_superuser):
        raise ErrorComercial({"proforma": "No puede modificar una proforma de otro vendedor."})
    return proforma


def _exigir_proforma_borrador(proforma: Proforma, campo: str = "proforma") -> None:
    if proforma.estado.codigo != "BORRADOR":
        raise ConflictoComercial(
            {campo: "Sólo una proforma BORRADOR admite modificaciones."}
        )


def _validar_modo(modo: str, importe_negociado):
    if modo not in {"PRECIO_UNITARIO", "TOTAL_NEGOCIADO"}:
        raise ErrorComercial({"modo_calculo": "Debe ser PRECIO_UNITARIO o TOTAL_NEGOCIADO."})
    if modo == "TOTAL_NEGOCIADO" and importe_negociado is None:
        raise ErrorComercial({"importe_negociado": "Es obligatorio para TOTAL_NEGOCIADO."})
    if modo == "PRECIO_UNITARIO" and importe_negociado is not None:
        raise ErrorComercial({"importe_negociado": "Sólo se admite en TOTAL_NEGOCIADO."})


def _precio_catalogo(proforma: Proforma, producto: Producto, datos: dict) -> dict:
    if proforma.moneda.codigo == "USD":
        if datos.get("precio_unitario") is None:
            raise ErrorComercial(
                {"precio_unitario": "Una cotización USD requiere precio explícito."}
            )
        return datos
    antes, ahora, descuento_unitario = precio_catalogo_vigente(producto)
    if descuento_unitario < 0:
        raise ErrorComercial({"producto": "La promoción tiene precios inconsistentes."})

    datos["precio_unitario"] = ahora
    datos["descuento"] = Decimal("0.00")
    if descuento_unitario > 0:
        datos["precio_antes_snapshot"] = antes
        datos["precio_ahora_snapshot"] = ahora
    else:
        datos["precio_antes_snapshot"] = None
        datos["precio_ahora_snapshot"] = None

    # Los snapshots ANTES/AHORA representan una promoción real; sin promoción quedan NULL.
    return datos


@transaction.atomic
def agregar_detalle(*, proforma_id: int, actor, **datos) -> DetalleProforma:
    proforma = _proforma_bloqueada(proforma_id, actor)
    _exigir_proforma_borrador(proforma)
    modo = datos.get("modo_calculo", "PRECIO_UNITARIO")
    _validar_modo(modo, datos.get("importe_negociado"))
    producto = datos.get("producto")
    if producto is None and datos.get("producto_id"):
        producto = Producto.objects.get(pk=datos["producto_id"])
    if producto is not None:
        datos = _precio_catalogo(proforma, producto, datos)
    return DetalleProforma.objects.create(proforma=proforma, **datos)


@transaction.atomic
def actualizar_detalle(*, detalle_id: int, actor, **datos) -> DetalleProforma:
    detalle = (
        DetalleProforma.objects.select_for_update().select_related("proforma").get(pk=detalle_id)
    )
    proforma = _proforma_bloqueada(detalle.proforma_id, actor)
    _exigir_proforma_borrador(proforma, "detalle")
    modo = datos.get("modo_calculo", detalle.modo_calculo)
    importe = datos.get("importe_negociado", detalle.importe_negociado)
    _validar_modo(modo, importe)
    for campo, valor in datos.items():
        setattr(detalle, campo, valor)
    if detalle.producto_id and detalle.proforma.moneda.codigo == "BOB":
        _precio_catalogo(detalle.proforma, detalle.producto, datos)
        for campo, valor in datos.items():
            setattr(detalle, campo, valor)
    detalle.save()
    return detalle


@transaction.atomic
def enviar_proforma(*, proforma_id: int, actor) -> Proforma:
    proforma = _proforma_bloqueada(proforma_id, actor)
    if proforma.estado.codigo != "BORRADOR":
        raise ConflictoComercial({"estado": "Sólo una proforma BORRADOR puede enviarse."})
    proforma.estado = valor_catalogo("ESTADO_PROFORMA", "ENVIADA")
    proforma.updated_by = actor
    proforma.save(update_fields=["estado", "updated_by"])
    proforma.refresh_from_db()
    return proforma


@transaction.atomic
def crear_especificacion(*, detalle_id: int, actor, **datos) -> EspecificacionMueble:
    detalle = (
        DetalleProforma.objects.select_for_update().select_related("proforma").get(pk=detalle_id)
    )
    proforma = _proforma_bloqueada(detalle.proforma_id, actor)
    _exigir_proforma_borrador(proforma, "detalle")
    return EspecificacionMueble.objects.create(proforma_detalle=detalle, **datos)


@transaction.atomic
def actualizar_proforma(*, proforma_id: int, actor, **datos) -> Proforma:
    proforma = _proforma_bloqueada(proforma_id, actor)
    _exigir_proforma_borrador(proforma)
    for campo, valor in datos.items():
        setattr(proforma, campo, valor)
    proforma.updated_by = actor
    proforma.save()
    return proforma
