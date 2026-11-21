import csv
import io
import uuid
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Case, DecimalField, F, Q, Sum, Value, When, Window
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.catalogo.models import Producto, ValorCatalogo
from apps.catalogo.services import validar_cantidad_segun_unidad
from apps.core.permissions import es_administrador_comercial
from apps.movimientos_stock.models import MovimientoStock

MOTIVO_CORRECCION_EXCEPCIONAL = "CORRECCION_EXCEPCIONAL"

MOTIVOS_ENTRADA: dict[str, str] = {
    "REPOSICION": "Reposición",
    "REGULARIZACION_POSITIVA": "Regularización positiva",
    MOTIVO_CORRECCION_EXCEPCIONAL: "Corrección excepcional",
}

MOTIVOS_SALIDA: dict[str, str] = {
    "MERMA": "Merma",
    "DANO": "Daño",
    "USO_INTERNO": "Uso interno",
    "REGULARIZACION_NEGATIVA": "Regularización negativa",
    MOTIVO_CORRECCION_EXCEPCIONAL: "Corrección excepcional",
}

TODOS_LOS_MOTIVOS: dict[str, str] = {**MOTIVOS_ENTRADA, **MOTIVOS_SALIDA}


def catalogo_motivos_ajuste() -> dict[str, list[dict[str, object]]]:
    return {
        "ENTRADA": [
            {
                "codigo": codigo,
                "nombre": nombre,
                "requiere_observaciones": codigo == MOTIVO_CORRECCION_EXCEPCIONAL,
            }
            for codigo, nombre in MOTIVOS_ENTRADA.items()
        ],
        "SALIDA": [
            {
                "codigo": codigo,
                "nombre": nombre,
                "requiere_observaciones": codigo == MOTIVO_CORRECCION_EXCEPCIONAL,
            }
            for codigo, nombre in MOTIVOS_SALIDA.items()
        ],
    }


def label_motivo(codigo: str | None) -> str | None:
    if not codigo:
        return None
    return TODOS_LOS_MOTIVOS.get(codigo, codigo)


def _sanitizar_celda_csv(valor: object) -> str:
    texto = "" if valor is None else str(valor)
    if texto and texto[0] in ("=", "@", "\t", "\r"):
        return f"'{texto}"
    return texto


def _normalizar_clave_idempotencia(clave: str | uuid.UUID | None) -> uuid.UUID | None:
    if clave is None or clave == "":
        return None
    if isinstance(clave, uuid.UUID):
        return clave
    try:
        return uuid.UUID(str(clave).strip())
    except ValueError as exc:
        raise ValidationError({"clave_idempotencia": "Debe ser un UUID válido."}) from exc


@transaction.atomic
def registrar_ajuste_stock(
    *,
    producto_id: int,
    tipo_operacion: str,
    cantidad: Decimal,
    motivo: str,
    observaciones: str | None,
    actor,
    clave_idempotencia: str | uuid.UUID | None = None,
) -> tuple[MovimientoStock, bool]:
    """Registra un ajuste manual (ENTRADA o SALIDA) de forma transaccional e idempotente."""
    if not es_administrador_comercial(actor):
        raise PermissionDenied("Solo la administración comercial puede registrar ajustes de stock.")

    clave_uuid = _normalizar_clave_idempotencia(clave_idempotencia)
    if clave_uuid is not None:
        existente = (
            MovimientoStock.objects.select_related(
                "producto",
                "producto__unidad_stock",
                "tipo_movimiento",
                "pedido",
                "movimiento_referencia__pedido",
                "created_by",
            )
            .filter(clave_idempotencia=clave_uuid)
            .first()
        )
        if existente is not None:
            return existente, True

    if tipo_operacion not in {"ENTRADA", "SALIDA"}:
        raise ValidationError({"tipo_operacion": "Debe ser ENTRADA o SALIDA."})

    motivos_validos = MOTIVOS_ENTRADA if tipo_operacion == "ENTRADA" else MOTIVOS_SALIDA
    if motivo not in motivos_validos:
        raise ValidationError({"motivo": f"Motivo inválido para {tipo_operacion}."})

    obs_limpia = (observaciones or "").strip()
    if motivo == MOTIVO_CORRECCION_EXCEPCIONAL and not obs_limpia:
        raise ValidationError(
            {
                "observaciones": (
                    "Las correcciones excepcionales requieren una observación justificativa."
                )
            }
        )

    try:
        producto = (
            Producto.objects.select_related("unidad_stock").select_for_update().get(pk=producto_id)
        )
    except Producto.DoesNotExist as exc:
        raise ValidationError({"producto": "El producto indicado no existe."}) from exc

    try:
        validar_cantidad_segun_unidad(cantidad, producto.unidad_stock.codigo, permitir_cero=False)
    except ValidationError as exc:
        raise ValidationError({"cantidad": exc.detail}) from exc

    cantidad_con_signo = cantidad if tipo_operacion == "ENTRADA" else -cantidad
    if tipo_operacion == "SALIDA" and (producto.stock + cantidad_con_signo) < 0:
        raise ValidationError(
            {
                "cantidad": (
                    f"Stock insuficiente para la salida. Stock actual: "
                    f"{producto.stock} {producto.unidad_stock.codigo}."
                )
            }
        )

    tipo_ajuste = ValorCatalogo.objects.get(
        concepto__codigo="TIPO_MOVIMIENTO",
        codigo="AJUSTE",
    )
    obs_final = obs_limpia or motivos_validos[motivo]

    try:
        with transaction.atomic():
            movimiento = MovimientoStock.objects.create(
                producto=producto,
                fecha=timezone.now(),
                tipo_movimiento=tipo_ajuste,
                cantidad=cantidad_con_signo,
                motivo=motivo,
                observaciones=obs_final,
                created_by=actor,
                clave_idempotencia=clave_uuid,
            )
    except IntegrityError:
        if clave_uuid is not None:
            existente = MovimientoStock.objects.select_related(
                "producto",
                "producto__unidad_stock",
                "tipo_movimiento",
                "pedido",
                "movimiento_referencia__pedido",
                "created_by",
            ).get(clave_idempotencia=clave_uuid)
            return existente, True
        raise

    movimiento = MovimientoStock.objects.select_related(
        "producto",
        "producto__unidad_stock",
        "tipo_movimiento",
        "pedido",
        "movimiento_referencia__pedido",
        "created_by",
    ).get(pk=movimiento.pk)
    return movimiento, False


def calcular_saldos_y_resumen(queryset_filtrado, *, producto_id: int | None) -> dict:
    """Calcula resumen del período y saldos históricos cuando existe un único producto confiable."""
    if producto_id is None:
        return {
            "saldo_reconstruible": False,
            "limitacion_saldo": (
                "Selecciona un producto específico para calcular saldos históricos "
                "y totales sin mezclar unidades."
            ),
            "resumen": None,
            "saldos_por_id": {},
        }

    producto = Producto.objects.select_related("unidad_stock").filter(pk=producto_id).first()
    if producto is None:
        return {
            "saldo_reconstruible": False,
            "limitacion_saldo": "El producto seleccionado no existe.",
            "resumen": None,
            "saldos_por_id": {},
        }

    agregados = queryset_filtrado.aggregate(
        total_entradas=Coalesce(
            Sum(
                Case(
                    When(cantidad__gt=0, then=F("cantidad")),
                    default=Value(Decimal("0")),
                    output_field=DecimalField(max_digits=14, decimal_places=4),
                )
            ),
            Value(Decimal("0")),
            output_field=DecimalField(max_digits=14, decimal_places=4),
        ),
        total_salidas=Coalesce(
            Sum(
                Case(
                    When(cantidad__lt=0, then=-F("cantidad")),
                    default=Value(Decimal("0")),
                    output_field=DecimalField(max_digits=14, decimal_places=4),
                )
            ),
            Value(Decimal("0")),
            output_field=DecimalField(max_digits=14, decimal_places=4),
        ),
        variacion_neta=Coalesce(
            Sum("cantidad"),
            Value(Decimal("0")),
            output_field=DecimalField(max_digits=14, decimal_places=4),
        ),
    )

    total_historico = MovimientoStock.objects.filter(producto_id=producto_id).aggregate(
        total=Coalesce(Sum("cantidad"), Value(Decimal("0")))
    )["total"]

    saldo_reconstruible = total_historico == producto.stock
    limitacion_saldo = None
    saldos_por_id: dict[int, dict[str, str]] = {}
    saldo_inicial_periodo: str | None = None
    saldo_final_periodo: str | None = None

    if saldo_reconstruible:
        movs_con_saldo = list(
            MovimientoStock.objects.filter(producto_id=producto_id)
            .annotate(
                saldo_posterior=Window(
                    expression=Sum("cantidad"),
                    order_by=[F("fecha").asc(), F("id").asc()],
                )
            )
            .values("id", "cantidad", "saldo_posterior")
        )
        for row in movs_con_saldo:
            saldo_post = row["saldo_posterior"]
            saldo_ant = saldo_post - row["cantidad"]
            saldos_por_id[row["id"]] = {
                "saldo_anterior": str(saldo_ant),
                "saldo_posterior": str(saldo_post),
            }

        ids_filtrados = list(queryset_filtrado.order_by("fecha", "id").values_list("id", flat=True))
        if ids_filtrados:
            primero = saldos_por_id.get(ids_filtrados[0])
            ultimo = saldos_por_id.get(ids_filtrados[-1])
            saldo_inicial_periodo = primero["saldo_anterior"] if primero else None
            saldo_final_periodo = ultimo["saldo_posterior"] if ultimo else None
    else:
        limitacion_saldo = (
            "Los movimientos históricos de este producto no coinciden exactamente con su stock "
            f"actual ({total_historico} vs {producto.stock}); no se inventarán saldos históricos."
        )

    return {
        "saldo_reconstruible": saldo_reconstruible,
        "limitacion_saldo": limitacion_saldo,
        "resumen": {
            "producto_id": producto.id,
            "unidad_codigo": producto.unidad_stock.codigo,
            "unidad_nombre": producto.unidad_stock.nombre,
            "stock_actual": str(producto.stock),
            "total_entradas": str(agregados["total_entradas"]),
            "total_salidas": str(agregados["total_salidas"]),
            "variacion_neta": str(agregados["variacion_neta"]),
            "saldo_inicial_periodo": saldo_inicial_periodo,
            "saldo_final_periodo": saldo_final_periodo,
            "cantidad_movimientos": queryset_filtrado.filter(Q(pk__isnull=False)).count(),
        },
        "saldos_por_id": saldos_por_id,
    }


def generar_csv_movimientos(movimientos, *, saldos_por_id: dict[int, dict[str, str]]) -> str:
    """Genera CSV UTF-8 con BOM compatible con Excel para los movimientos filtrados."""
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "ID",
            "Fecha",
            "SKU",
            "Producto",
            "Unidad",
            "Tipo",
            "Dirección",
            "Cantidad",
            "Motivo",
            "Observaciones",
            "Pedido",
            "Movimiento Referencia",
            "Responsable",
            "Saldo Anterior",
            "Saldo Posterior",
        ]
    )

    for mov in movimientos:
        responsable = (
            mov.created_by.get_full_name().strip() or mov.created_by.get_username()
            if mov.created_by
            else "Sistema"
        )
        pedido_rel = mov.pedido_id
        if pedido_rel is None and mov.tipo_movimiento.codigo == "REVERSA_VENTA":
            ref = mov.movimiento_referencia
            pedido_rel = ref.pedido_id if ref is not None else None
        saldos = saldos_por_id.get(mov.id)
        direccion = "Entrada" if mov.cantidad > 0 else "Salida"
        writer.writerow(
            [
                mov.id,
                timezone.localtime(mov.fecha).strftime("%Y-%m-%d %H:%M:%S"),
                _sanitizar_celda_csv(mov.producto.sku or ""),
                _sanitizar_celda_csv(mov.producto.nombre),
                _sanitizar_celda_csv(mov.producto.unidad_stock.nombre),
                _sanitizar_celda_csv(mov.tipo_movimiento.nombre),
                direccion,
                str(mov.cantidad),
                _sanitizar_celda_csv(label_motivo(mov.motivo) or ""),
                _sanitizar_celda_csv(mov.observaciones or ""),
                pedido_rel or "",
                mov.movimiento_referencia_id or "",
                _sanitizar_celda_csv(responsable),
                saldos["saldo_anterior"] if saldos else "",
                saldos["saldo_posterior"] if saldos else "",
            ]
        )
    return buffer.getvalue()
