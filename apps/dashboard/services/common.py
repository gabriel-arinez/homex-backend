from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek
from django.utils import timezone

from apps.core.tiempo_comercial import fecha_comercial_actual, fecha_hora_comercial_simulada
from apps.dashboard.filters import Granularidad

TZ_LA_PAZ = ZoneInfo("America/La_Paz")
FECHA_CORTE_EVALUACION = date(2026, 11, 27)
DOS_DECIMALES = Decimal("0.01")
CERO = Decimal("0.00")


def fecha_referencia_analitica() -> date:
    """Devuelve la fecha de corte comercial vigente (simulada, evaluación o real)."""
    if fecha_hora_comercial_simulada() is not None:
        return fecha_comercial_actual(timezone.localdate)
    simulada = fecha_comercial_actual(lambda: None)  # type: ignore[arg-type, return-value]
    if simulada is not None:
        return simulada
    if getattr(settings, "HOMEX_ENTORNO_EVALUACION", False):
        return FECHA_CORTE_EVALUACION
    return timezone.localdate()


def redondear_decimal(valor: Decimal | int | float | None) -> Decimal:
    if valor is None:
        return CERO
    return Decimal(str(valor)).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)


def calcular_porcentaje(numerador: Decimal | int, denominador: Decimal | int) -> Decimal | None:
    """Devuelve porcentaje (0-100) o None si el denominador es cero."""
    den = Decimal(str(denominador))
    if den == 0:
        return None
    num = Decimal(str(numerador))
    return ((num * Decimal("100")) / den).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)


def periodo_anterior(
    fecha_desde: date | None, fecha_hasta: date | None
) -> tuple[date, date] | None:
    """Calcula el período comparable inmediatamente anterior de igual duración."""
    if fecha_desde is None or fecha_hasta is None:
        return None
    dias = (fecha_hasta - fecha_desde).days
    prev_hasta = fecha_desde - timedelta(days=1)
    prev_desde = prev_hasta - timedelta(days=dias)
    return prev_desde, prev_hasta


def variacion_numerica(
    actual: int | Decimal,
    anterior: int | Decimal | None,
) -> dict:
    if anterior is None:
        return {
            "actual": actual,
            "anterior": None,
            "diferencia": None,
            "variacion_porcentaje": None,
        }
    diferencia = actual - anterior
    porcentaje = calcular_porcentaje(diferencia, anterior) if anterior != 0 else None
    return {
        "actual": actual,
        "anterior": anterior,
        "diferencia": diferencia,
        "variacion_porcentaje": porcentaje,
    }


def trunc_temporal(field_name: str, granularidad: Granularidad, *, is_datetime: bool):
    """Construye la expresión TruncDay/TruncWeek/TruncMonth en zona horaria America/La_Paz."""
    kwargs = {"tzinfo": TZ_LA_PAZ} if is_datetime else {}
    if granularidad == "diaria":
        return TruncDay(field_name, **kwargs)
    if granularidad == "semanal":
        return TruncWeek(field_name, **kwargs)
    return TruncMonth(field_name, **kwargs)


def inicio_dia_la_paz(fecha: date) -> datetime:
    return datetime.combine(fecha, time.min, tzinfo=TZ_LA_PAZ)


def fin_dia_la_paz(fecha: date) -> datetime:
    return datetime.combine(fecha, time.max, tzinfo=TZ_LA_PAZ)


def formatear_periodo(valor) -> str:
    if isinstance(valor, datetime):
        return valor.astimezone(TZ_LA_PAZ).date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)


def nombre_cliente_proforma(proforma) -> str:
    if proforma.cliente_nombre_snapshot:
        return proforma.cliente_nombre_snapshot.strip()
    if proforma.cliente_id is not None:
        cliente = proforma.cliente
        nombre = " ".join(
            p.strip() for p in [cliente.nombres or "", cliente.apellidos or ""] if p.strip()
        )
        if nombre:
            return nombre
        if cliente.empresa:
            return cliente.empresa.strip()
    if proforma.prospecto_nombre:
        return proforma.prospecto_nombre.strip()
    if proforma.prospecto_empresa:
        return proforma.prospecto_empresa.strip()
    return "Sin cliente"


def nombre_usuario(user) -> str:
    if user is None:
        return ""
    return user.get_full_name().strip() or user.get_username()


def paginar_lista(items: list, page: int, page_size: int) -> dict:
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "results": items[start:end],
    }
