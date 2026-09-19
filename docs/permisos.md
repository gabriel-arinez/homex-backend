# Permisos

La aplicación usa el grupo Django `VENDEDOR`: consulta y opera su propio flujo
comercial. `is_staff` o `is_superuser` administra catálogo y consulta datos de
cualquier vendedor. Usuarios sin rol reciben 403.

En PostgreSQL se separan `homex_migrator` (DDL y migraciones) y `homex_runtime`
(DML mínimo). El procedimiento idempotente está en `docs/sql/privilegios_runtime.sql`.
Las credenciales se inyectan mediante `DATABASE_URL`; nunca se almacenan aquí.
