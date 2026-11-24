"""Explicit, isolated commercial clock for chronological simulation replay."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date

from django.utils import timezone

_FECHA_COMERCIAL_SIMULADA: ContextVar[date | None] = ContextVar(
    "homex_fecha_comercial_simulada",
    default=None,
)


def fecha_comercial_actual(fallback: Callable[[], date] | None = None) -> date:
    """Return the active simulated commercial date or the real local date."""
    simulada = _FECHA_COMERCIAL_SIMULADA.get()
    if simulada is not None:
        return simulada
    return (fallback or timezone.localdate)()


@contextmanager
def reloj_comercial_simulado(fecha: date):
    """Temporarily set an isolated commercial business date without altering audit clocks."""
    if not isinstance(fecha, date):
        raise TypeError("La fecha comercial simulada debe ser una instancia de datetime.date.")
    token = _FECHA_COMERCIAL_SIMULADA.set(fecha)
    try:
        yield fecha
    finally:
        _FECHA_COMERCIAL_SIMULADA.reset(token)
