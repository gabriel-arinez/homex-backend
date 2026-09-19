-- Ejecutar como propietario/migrador de PostgreSQL, nunca con el usuario runtime.
-- Sustituir homex_runtime y homex_migrator por las cuentas provisionadas en cada entorno.
REVOKE ALL ON DATABASE homex FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE homex TO homex_runtime, homex_migrator;
GRANT USAGE ON SCHEMA public TO homex_runtime, homex_migrator;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO homex_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO homex_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE homex_migrator IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO homex_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE homex_migrator IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO homex_runtime;
-- homex_runtime no recibe CREATE, ALTER, DROP, ownership ni permisos de migración.
