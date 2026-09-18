# Runbook

1. Definir `DJANGO_SECRET_KEY`, `DATABASE_URL`, hosts y CORS fuera de Git.
2. Ejecutar `uv sync --locked --extra dev` y `uv run python manage.py migrate`.
3. Ejecutar `uv run python manage.py seed_roles`.
4. Verificar con `make check` y `make schema`.
5. Antes de producción, aplicar `docs/database/runtime-role.sql` con un rol propietario/migrador y usar el rol runtime para la API.

La carga real de sillas requiere la ficha comercial confirmada y debe ejecutarse primero con `--dry-run`.
