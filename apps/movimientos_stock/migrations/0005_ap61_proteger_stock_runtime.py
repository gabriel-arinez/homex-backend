"""AP6.1: el trigger de movimiento actualiza stock con privilegios del migrador.

El runtime no necesita UPDATE(stock): la función ejecuta la operación validada
en PostgreSQL. No se altera la lógica de movimientos ni datos históricos.
"""

from django.db import migrations


SQL = """
-- El owner de la función es el rol que aplicó las migraciones (migrador).
-- El search_path seguro impide resolver objetos mediante esquemas del caller.
ALTER FUNCTION public.fn_actualizar_stock_desde_movimiento()
    SECURITY DEFINER;
ALTER FUNCTION public.fn_actualizar_stock_desde_movimiento()
    SET search_path = pg_catalog, public, pg_temp;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("movimientos_stock", "0004_alter_movimientostock_cantidad"),
        ("proformas", "0011_ap3_idempotencia_guardado_integral"),
    ]

    operations = [
        # La reversión no debe reabrir la vulnerabilidad de privilegios.
        migrations.RunSQL(sql=SQL, reverse_sql=migrations.RunSQL.noop),
    ]
