import pytest
from django.db import connection

from apps.capturas.bloqueo_ejecucion import NAMESPACE_CAPTURAS, bloqueo_intento


@pytest.mark.django_db(transaction=True)
def test_conexion_reemplazada_no_libera_bloqueo_de_nueva_sesion():
    intento_id = 193847

    with bloqueo_intento(intento_id) as adquirido:
        assert adquirido is True
        sesion_original = connection.connection

        # Cierra la sesión original y su bloqueo PostgreSQL.
        connection.close()

        # Fuerza una sesión física nueva.
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_try_advisory_lock(%s, %s)",
                [NAMESPACE_CAPTURAS, intento_id],
            )
            assert cursor.fetchone()[0] is True

        sesion_nueva = connection.connection
        assert sesion_nueva is not sesion_original

        try:
            # El context manager antiguo no debe desbloquear
            # una sesión diferente.
            pass
        finally:
            # La liberación real se comprueba fuera del contexto.
            pass

    # Si el contexto antiguo hubiera liberado el nuevo bloqueo,
    # PostgreSQL devolvería False aquí.
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_unlock(%s, %s)",
            [NAMESPACE_CAPTURAS, intento_id],
        )
        assert cursor.fetchone()[0] is True

        cursor.execute(
            "SELECT pg_advisory_unlock(%s, %s)",
            [NAMESPACE_CAPTURAS, intento_id],
        )
        assert cursor.fetchone()[0] is False
