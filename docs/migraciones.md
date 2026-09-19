# Migraciones

Ejecutar con el usuario `homex_migrator`: `uv run python manage.py migrate --noinput`.
Antes de producción, ensayar backup, restauración, migración y smoke test. No usar
`--fake` para corregir divergencias. El usuario runtime no ejecuta migraciones.
