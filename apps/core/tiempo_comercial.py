"""Explicit, isolated commercial clock for chronological simulation replay."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime

from django.db import connection
from django.utils import timezone

_FECHA_COMERCIAL_SIMULADA: ContextVar[date | None] = ContextVar(
    "homex_fecha_comercial_simulada",
    default=None,
)
_FECHA_HORA_COMERCIAL_SIMULADA: ContextVar[datetime | None] = ContextVar(
    "homex_fecha_hora_comercial_simulada",
    default=None,
)


def fecha_comercial_actual(fallback: Callable[[], date] | None = None) -> date:
    """Return the active simulated commercial date or the real local date."""
    simulada = _FECHA_COMERCIAL_SIMULADA.get()
    if simulada is not None:
        return simulada
    return (fallback or timezone.localdate)()


def fecha_hora_comercial_simulada() -> datetime | None:
    """Return the active simulated business datetime, or None outside simulation."""
    return _FECHA_HORA_COMERCIAL_SIMULADA.get()


def fecha_hora_comercial_actual() -> datetime:
    """Return the active simulated commercial datetime or the current real timestamp."""
    return fecha_hora_comercial_simulada() or timezone.now()


def establecer_reloj_pg_transaccional(fecha_hora: datetime | None) -> None:
    """Set transaction-local PostgreSQL GUC without leaking across connections."""
    with connection.cursor() as cursor:
        if fecha_hora is None:
            cursor.execute("SET LOCAL homex.fecha_comercial_simulada = ''")
        else:
            cursor.execute(
                "SELECT set_config('homex.fecha_comercial_simulada', %s, true)",
                [fecha_hora.isoformat()],
            )


@contextmanager
def reloj_comercial_simulado(fecha: date, *, fecha_hora: datetime | None = None):
    """Temporarily set an isolated commercial business clock without altering audit clocks."""
    if not isinstance(fecha, date):
        raise TypeError("La fecha comercial simulada debe ser una instancia de datetime.date.")
    token_fecha = _FECHA_COMERCIAL_SIMULADA.set(fecha)
    token_dt = _FECHA_HORA_COMERCIAL_SIMULADA.set(fecha_hora)
    if fecha_hora is not None and connection.in_atomic_block:
        establecer_reloj_pg_transaccional(fecha_hora)
    try:
        yield fecha
    finally:
        if fecha_hora is not None and connection.in_atomic_block:
            establecer_reloj_pg_transaccional(None)
        _FECHA_HORA_COMERCIAL_SIMULADA.reset(token_dt)
        _FECHA_COMERCIAL_SIMULADA.reset(token_fecha)
