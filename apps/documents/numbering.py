from django.db import connection
from django.db.models import Max


def next_commercial_number(*, sequence_name: str, model, field_name: str = "number") -> int:
    """Obtiene un consecutivo comercial sin usar MAX+1 en PostgreSQL."""
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT nextval(%s::regclass)", [sequence_name])
            return cursor.fetchone()[0]

    # SQLite sólo se utiliza en pruebas aisladas, donde no ofrece secuencias PostgreSQL.
    current = model.objects.select_for_update().aggregate(value=Max(field_name))["value"]
    return (current or 0) + 1
