from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from django.utils.dateparse import parse_date
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.catalogo.models import ValorCatalogo

ScopeDashboard = Literal["admin", "tienda", "taller"]
Granularidad = Literal["diaria", "semanal", "mensual"]

GRANULARIDADES_VALIDAS = {"diaria", "semanal", "mensual"}


@dataclass(frozen=True)
class DashboardFilterParams:
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    granularidad: Granularidad = "mensual"
    vendedor_id: int | None = None
    moneda: str | None = None
    categoria: str | None = None
    estado_comercial: str | None = None
    estado_comercial_ambito: Literal["PROFORMA", "PEDIDO"] | None = None
    estado_fabricacion: str | None = None
    tipo_mueble: str | None = None
    entrega_desde: date | None = None
    entrega_hasta: date | None = None
    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def _parse_optional_date(raw: str | None, field_name: str) -> date | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        parsed = parse_date(raw.strip())
    except ValueError as exc:
        raise ValidationError(
            {field_name: "Fecha inválida. Use una fecha real YYYY-MM-DD."}
        ) from exc
    if parsed is None:
        raise ValidationError({field_name: "Formato de fecha inválido. Use YYYY-MM-DD."})
    return parsed


def _parse_positive_int(
    raw: str | None, field_name: str, *, default: int | None = None
) -> int | None:
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = int(str(raw).strip())
    except ValueError as exc:
        raise ValidationError({field_name: "Debe ser un número entero válido."}) from exc
    if value < 1:
        raise ValidationError({field_name: "Debe ser mayor o igual a 1."})
    return value


def _validate_catalog_code(concepto: str, raw: str | None, field_name: str) -> str | None:
    if raw is None or raw.strip() == "":
        return None
    code = raw.strip().upper()
    if not ValorCatalogo.objects.filter(concepto__codigo=concepto, codigo=code).exists():
        raise ValidationError({field_name: f"Código inválido para {concepto}: {code}."})
    return code


def parse_dashboard_filters(request, *, scope: ScopeDashboard) -> DashboardFilterParams:
    params = request.query_params

    fecha_desde = _parse_optional_date(params.get("fecha_desde"), "fecha_desde")
    fecha_hasta = _parse_optional_date(params.get("fecha_hasta"), "fecha_hasta")
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        raise ValidationError({"fecha_desde": "fecha_desde no puede ser posterior a fecha_hasta."})

    granularidad_raw = (params.get("granularidad") or "mensual").strip().lower()
    if granularidad_raw not in GRANULARIDADES_VALIDAS:
        raise ValidationError(
            {"granularidad": "Granularidad inválida. Use diaria, semanal o mensual."}
        )
    granularidad: Granularidad = granularidad_raw  # type: ignore[assignment]

    vendedor_raw = params.get("vendedor")
    vendedor_id: int | None = None
    if vendedor_raw is not None and str(vendedor_raw).strip() != "":
        if scope == "tienda":
            parsed_v = _parse_positive_int(vendedor_raw, "vendedor")
            if parsed_v != request.user.id:
                raise PermissionDenied(
                    "No puede consultar indicadores personales de otro vendedor."
                )
            vendedor_id = request.user.id
        elif scope == "taller":
            raise ValidationError(
                {"vendedor": "El filtro de vendedor no aplica al dashboard de taller."}
            )
        else:
            vendedor_id = _parse_positive_int(vendedor_raw, "vendedor")

    if scope == "tienda":
        vendedor_id = request.user.id

    moneda = None
    categoria = None
    estado_comercial = None
    estado_comercial_ambito: Literal["PROFORMA", "PEDIDO"] | None = None
    if scope != "taller":
        moneda = _validate_catalog_code("MONEDA", params.get("moneda"), "moneda")
        categoria = _validate_catalog_code(
            "CATEGORIA_PRODUCTO", params.get("categoria"), "categoria"
        )
        raw_est_com = params.get("estado_comercial")
        if raw_est_com is not None and raw_est_com.strip() != "":
            code = raw_est_com.strip().upper()
            valor_est = (
                ValorCatalogo.objects.select_related("concepto")
                .filter(
                    concepto__codigo__in=["ESTADO_PROFORMA", "ESTADO_PEDIDO"],
                    codigo=code,
                )
                .first()
            )
            if valor_est is None:
                raise ValidationError({"estado_comercial": f"Estado comercial inválido: {code}."})
            estado_comercial = code
            estado_comercial_ambito = (
                "PROFORMA" if valor_est.concepto.codigo == "ESTADO_PROFORMA" else "PEDIDO"
            )

    estado_fabricacion = _validate_catalog_code(
        "ESTADO_ORDEN_TRABAJO", params.get("estado_fabricacion"), "estado_fabricacion"
    )
    tipo_mueble = _validate_catalog_code("TIPO_MUEBLE", params.get("tipo_mueble"), "tipo_mueble")

    entrega_desde = _parse_optional_date(params.get("entrega_desde"), "entrega_desde")
    entrega_hasta = _parse_optional_date(params.get("entrega_hasta"), "entrega_hasta")
    if entrega_desde and entrega_hasta and entrega_desde > entrega_hasta:
        raise ValidationError(
            {"entrega_desde": "entrega_desde no puede ser posterior a entrega_hasta."}
        )

    page = _parse_positive_int(params.get("page"), "page", default=1) or 1
    page_size = _parse_positive_int(params.get("page_size"), "page_size", default=20) or 20
    if page_size > 100:
        raise ValidationError({"page_size": "page_size no puede superar 100."})

    return DashboardFilterParams(
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        granularidad=granularidad,
        vendedor_id=vendedor_id,
        moneda=moneda,
        categoria=categoria,
        estado_comercial=estado_comercial,
        estado_comercial_ambito=estado_comercial_ambito,
        estado_fabricacion=estado_fabricacion,
        tipo_mueble=tipo_mueble,
        entrega_desde=entrega_desde,
        entrega_hasta=entrega_hasta,
        page=page,
        page_size=page_size,
    )
