# F07.0 — Baseline seguro y nomenclatura congelada

## Base

- Rama: `main`.
- Commit base: `503c46c` (`docs: redefine production-safe backend master plan`).
- Alcance: configuración, apps definitivas, autenticación, health, dependencias, CI y nomenclatura.

## Implementación

- Se adoptaron `pyproject.toml` y `uv.lock` para Python `>=3.11,<3.12`; `requirements.txt` fue retirado para evitar una segunda fuente de dependencias.
- Se configuraron los perfiles `base`, `local`, `test` y `production`, todos con contrato `DATABASE_URL` de PostgreSQL.
- Se creó `accounts.User` sobre `AbstractUser` y su migración inicial antes de cualquier migración comercial.
- Las apps comerciales definitivas quedan normalizadas: `catalogo`, `clientes`, `proformas`, `pedidos`, `movimientos_stock`, `ordenes_trabajo`, `recibos`, `notas_entrega`, `documentos` y `capturas`.
- Se retiraron las apps provisionales `ventas`, `taller`, `entregas`, `pagos` y `nlp`. No se crearon modelos ni migraciones comerciales.
- Se añadieron DRF, JWT, CORS, OpenAPI, `/api/v1/health/`, rutas JWT, `.env.example`, `Makefile`, `README.md` y CI por jobs independientes.

## Migraciones

- Creada: `apps/accounts/migrations/0001_initial.py`.
- Migraciones comerciales: ninguna, por diseño de F07.0.

## Evidencia local

Ejecutado sobre PostgreSQL temporal vacío:

- `uv sync --locked --extra dev`: correcto.
- `ruff check .`: correcto.
- `ruff format --check .`: correcto.
- `manage.py check`: correcto.
- `manage.py makemigrations --check --dry-run`: sin cambios.
- `manage.py migrate --noinput`: correcto.
- Segunda ejecución de `migrate --noinput`: sin migraciones pendientes.
- `pytest -ra`: `4 passed`.
- `spectacular --validate` y diff con `docs/openapi.yaml`: correctos.

No existen skips de pruebas obligatorias para F07.0. El job de concurrencia ejecuta una prueba de infraestructura contra PostgreSQL; las pruebas concurrentes de negocio pertenecen a F07.2–F07.4.

## Riesgos y cierre

No se integraron Celery, Redis, modelos comerciales ni NLP, conforme al alcance. El único gate externo pendiente es la ejecución remota de GitHub Actions, que requiere que el usuario cree el commit y publique estos cambios. F07.0 no debe declararse cerrada hasta que esos jobs estén verdes.
