# HOMEX Backend

Backend Django/DRF del flujo comercial HOMEX. PostgreSQL es obligatorio desde el inicio; las migraciones Django son la fuente operativa del esquema.

## Inicio local

1. Use Python 3.11.15 y copie `.env.example` a `.env`.
2. Inicie PostgreSQL y defina `DATABASE_URL`.
3. Ejecute `uv sync --locked --extra dev`.
4. Ejecute `uv run python manage.py migrate` y `uv run python manage.py runserver`.

Comandos habituales: `make lint`, `make format`, `make check`, `make test` y `make schema`.

El plan de ejecución está en `docs/PLAN_MAESTRO_BACKEND_HOMEX.md`.
