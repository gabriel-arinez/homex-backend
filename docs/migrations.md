# Migraciones

Las migraciones Django son la fuente operativa. `homex_bd_final_v3.sql` sólo sirve de referencia y no debe ejecutarse sobre una base migrada.

Ejecutar desde vacío con `uv run python manage.py migrate --noinput`. Las migraciones PostgreSQL añaden secuencias comerciales y triggers para recibos, stock y movimientos; SQLite se utiliza únicamente para pruebas rápidas y no sustituye esas verificaciones.
