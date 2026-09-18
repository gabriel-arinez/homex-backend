from django.db import connection
from django.db.models import Max


def siguiente_numero_comercial(*, sequence_nombre: str, modelo, field_nombre: str = "numero") -> int:
    """Obtiene un consecutivo comercial sin usar MAX+1 en PostgreSQL."""
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT nextval(%s::regclass)", [sequence_nombre])
            return cursor.fetchone()[0]

    # SQLite sólo se utiliza en pruebas aisladas, donde no ofrece secuencias PostgreSQL.
    current = modelo.objects.select_for_update().aggregate(value=Max(field_nombre))["value"]
    return (current or 0) + 1
