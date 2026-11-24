import uuid
from decimal import Decimal

from django.db import DatabaseError, IntegrityError, connection, transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core.db_errors import traducir_error_comercial_postgresql
from apps.core.exceptions import ConflictoComercial
from apps.core.tiempo_comercial import fecha_comercial_actual
from apps.recibos.models import Recibo


def _numero():
    with connection.cursor() as c:
        c.execute("SELECT nextval('seq_recibos_numero')")
        return c.fetchone()[0]


def _autorizar_pedido(*, pedido, actor):
    if actor.is_staff or actor.is_superuser:
        return

    if pedido.proforma.vendedor_id != actor.id:
        raise PermissionDenied("El pedido no pertenece al vendedor autenticado.")


def _normalizar_clave_idempotencia(clave: str | uuid.UUID | None) -> uuid.UUID | None:
    if clave is None or str(clave).strip() == "":
        return None
    if isinstance(clave, uuid.UUID):
        return clave
    try:
        return uuid.UUID(str(clave).strip())
    except ValueError as exc:
        raise ValidationError({"clave_idempotencia": "Debe ser un UUID válido."}) from exc


def _verificar_payload_recibo_idempotente(
    existente: Recibo,
    *,
    actor_id: int,
    pedido_id: int,
    nombre_completo: str,
    monto_en_letras: str,
    concepto: str,
    tipo_pago_id: int,
    numero_cheque: str | None,
    banco: str | None,
    pago_actual: Decimal,
) -> None:
    coincide = (
        existente.created_by_id == actor_id
        and existente.pedido_id == pedido_id
        and existente.nombre_completo == nombre_completo
        and existente.monto_en_letras == monto_en_letras
        and existente.concepto == concepto
        and existente.tipo_pago_id == tipo_pago_id
        and (existente.numero_cheque or "") == (numero_cheque or "")
        and (existente.banco or "") == (banco or "")
        and existente.pago_actual == pago_actual
    )
    if not coincide:
        raise ConflictoComercial(
            "La clave de idempotencia ya fue utilizada con un cobro diferente."
        )


@transaction.atomic
def emitir_recibo_idempotente(
    *,
    pedido,
    actor,
    clave_idempotencia: str | uuid.UUID | None = None,
    **datos,
) -> tuple[Recibo, bool]:
    pedido = (
        pedido.__class__.objects.select_related("proforma").select_for_update().get(pk=pedido.pk)
    )

    _autorizar_pedido(
        pedido=pedido,
        actor=actor,
    )

    clave_uuid = _normalizar_clave_idempotencia(clave_idempotencia)

    pago_actual = Decimal(str(datos["pago_actual"]))
    if pago_actual <= 0:
        raise ValidationError({"pago_actual": "El importe debe ser mayor a cero."})

    nombre_completo = (datos.get("nombre_completo") or "").strip()
    monto_en_letras = (datos.get("monto_en_letras") or "").strip()
    concepto = (datos.get("concepto") or "").strip()
    if not nombre_completo:
        raise ValidationError({"nombre_completo": "Indica el nombre del pagador."})
    if not monto_en_letras:
        raise ValidationError({"monto_en_letras": "Indica el monto en letras."})
    if not concepto:
        raise ValidationError({"concepto": "Indica el concepto del recibo."})

    tipo_pago = datos["tipo_pago"]
    if tipo_pago.concepto.codigo != "TIPO_PAGO" or not tipo_pago.activo:
        raise ValidationError({"tipo_pago": "El tipo de pago no es válido o está inactivo."})

    numero_cheque = (datos.get("numero_cheque") or "").strip() or None
    banco = (datos.get("banco") or "").strip() or None
    if tipo_pago.codigo == "CHEQUE":
        if not numero_cheque:
            raise ValidationError({"numero_cheque": "El número de cheque es obligatorio."})
        if not banco:
            raise ValidationError({"banco": "El banco es obligatorio para pagos con cheque."})
    else:
        numero_cheque = None
        banco = None

    if clave_uuid is not None:
        existente = (
            Recibo.objects.select_related("pedido__proforma__moneda", "tipo_pago")
            .filter(clave_idempotencia=clave_uuid)
            .first()
        )
        if existente is not None:
            _verificar_payload_recibo_idempotente(
                existente,
                actor_id=actor.id,
                pedido_id=pedido.id,
                nombre_completo=nombre_completo,
                monto_en_letras=monto_en_letras,
                concepto=concepto,
                tipo_pago_id=tipo_pago.id,
                numero_cheque=numero_cheque,
                banco=banco,
                pago_actual=pago_actual,
            )
            return existente, True

    datos_limpios = {
        "nombre_completo": nombre_completo,
        "monto_en_letras": monto_en_letras,
        "concepto": concepto,
        "tipo_pago": tipo_pago,
        "numero_cheque": numero_cheque,
        "banco": banco,
        "pago_actual": pago_actual,
    }

    try:
        with transaction.atomic():
            recibo = Recibo.objects.create(
                numero=_numero(),
                pedido=pedido,
                fecha=fecha_comercial_actual(),
                created_by=actor,
                updated_by=actor,
                clave_idempotencia=clave_uuid,
                **datos_limpios,
            )
    except IntegrityError as exc:
        if clave_uuid is not None:
            existente = (
                Recibo.objects.select_related("pedido__proforma__moneda", "tipo_pago")
                .filter(clave_idempotencia=clave_uuid)
                .first()
            )
            if existente is not None:
                _verificar_payload_recibo_idempotente(
                    existente,
                    actor_id=actor.id,
                    pedido_id=pedido.id,
                    nombre_completo=nombre_completo,
                    monto_en_letras=monto_en_letras,
                    concepto=concepto,
                    tipo_pago_id=tipo_pago.id,
                    numero_cheque=numero_cheque,
                    banco=banco,
                    pago_actual=pago_actual,
                )
                return existente, True
        traducir_error_comercial_postgresql(exc, "recibo")
    except DatabaseError as exc:
        traducir_error_comercial_postgresql(
            exc,
            "recibo",
        )

    # PostgreSQL calcula total, acumulado y saldo.
    recibo.refresh_from_db()
    return recibo, False


@transaction.atomic
def emitir_recibo(*, pedido, actor, **datos):
    recibo, _ = emitir_recibo_idempotente(pedido=pedido, actor=actor, **datos)
    return recibo


@transaction.atomic
def anular_recibo(*, recibo_id, actor):
    recibo = Recibo.objects.select_related("pedido__proforma").select_for_update().get(pk=recibo_id)

    _autorizar_pedido(
        pedido=recibo.pedido,
        actor=actor,
    )

    if recibo.estado != "EMITIDO":
        raise ValidationError(
            {
                "estado": "El recibo ya está anulado.",
            }
        )

    recibo.estado = "ANULADO"
    recibo.updated_by = actor

    try:
        recibo.save(
            update_fields=[
                "estado",
                "updated_by",
            ]
        )
    except DatabaseError as exc:
        traducir_error_comercial_postgresql(
            exc,
            "anulacion",
        )

    return recibo
