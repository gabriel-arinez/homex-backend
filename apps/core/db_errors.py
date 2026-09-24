from django.db import DatabaseError
from rest_framework.exceptions import ValidationError


def traducir_error_comercial_postgresql(
    exc: DatabaseError,
    campo: str,
):
    """
    Convierte únicamente los RAISE EXCEPTION comerciales de PostgreSQL
    (SQLSTATE P0001) en ValidationError de DRF.

    Los errores técnicos o inesperados conservan DatabaseError.
    """
    causa = exc.__cause__
    sqlstate = getattr(causa, "sqlstate", None)

    if sqlstate == "P0001":
        mensaje = str(causa).splitlines()[0]

        raise ValidationError(
            {
                campo: mensaje,
            }
        ) from exc

    raise exc
