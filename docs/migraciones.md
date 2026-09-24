# Migraciones PostgreSQL — HOMEX

## Fuente operativa del esquema

Las migraciones Django son la fuente operativa del esquema actual del backend.

PostgreSQL es obligatorio. No se admite SQLite como sustituto para los gates
comerciales.

## Instalación desde cero

Una base PostgreSQL vacía debe poder reconstruirse ejecutando:

```bash
uv run python manage.py migrate --noinput