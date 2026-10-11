"""Exclusión de procesamiento por intento mediante PostgreSQL."""

from contextlib import contextmanager

from django.db import connection

# Espacio de nombres exclusivo para los bloqueos del pipeline.
NAMESPACE_CAPTURAS = 202607


@contextmanager
def bloqueo_intento(intento_id: int):
    """Retiene un advisory lock de sesión durante toda la ejecución.

    Devuelve False cuando otra conexión ya procesa el mismo intento.
    PostgreSQL libera el bloqueo al cerrarse la conexión.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_try_advisory_lock(%s, %s)",
            [NAMESPACE_CAPTURAS, intento_id],
        )
        adquirido = cursor.fetchone()[0]

    if not adquirido:
        yield False
        return

    # El bloqueo pertenece a esta conexión física PostgreSQL.
    conexion_original = connection.connection

    try:
        yield True
    finally:
        # Si Django cerró o reemplazó la conexión, PostgreSQL
        # ya liberó su bloqueo de sesión.
        if connection.connection is conexion_original and not conexion_original.closed:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_unlock(%s, %s)",
                    [NAMESPACE_CAPTURAS, intento_id],
                )
                liberado = cursor.fetchone()[0]
                if not liberado:
                    raise RuntimeError(f"Se perdió el bloqueo del intento {intento_id}")
