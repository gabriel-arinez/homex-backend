# F07.0 — Saneamiento y baseline ejecutable

El backend ahora utiliza módulos canónicos bajo `apps/`, settings separados y
un usuario propio `accounts.User` antes de cualquier migración comercial.

- `config.settings.base` exige `DJANGO_SECRET_KEY` y `DATABASE_URL`; no contiene
  secretos ni credenciales por defecto.
- `config.settings.local` configura desarrollo a partir de `.env`.
- `config.settings.test` usa SQLite en memoria, aislada de PostgreSQL/Redis.
- `/api/v1/health/` es público; JWT expone token y refresh sin habilitar aún
  endpoints comerciales.
- `uv.lock`, Makefile y CI fijan instalación, lint, check y tests.

F07.0 no crea las tablas comerciales ni ejecuta `homex_bd_final_v3.sql`. La
siguiente fase, F07.1, trasladará el esquema a migraciones Django desde una
PostgreSQL vacía.
