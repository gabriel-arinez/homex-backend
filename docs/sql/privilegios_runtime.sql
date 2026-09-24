/*
 * HOMEX — privilegios mínimos del rol runtime.
 *
 * Precondiciones:
 *
 * 1. La base ya fue creada.
 * 2. Todas las migraciones fueron ejecutadas por el rol migrador.
 * 3. Esta sesión está conectada como el rol migrador/propietario.
 * 4. Antes de ejecutar este archivo deben definirse:
 *
 *      homex.migrator_role
 *      homex.runtime_role
 *
 * Ejemplo:
 *
 *   SELECT set_config(
 *       'homex.migrator_role',
 *       'homex_migrator',
 *       false
 *   );
 *
 *   SELECT set_config(
 *       'homex.runtime_role',
 *       'homex_runtime',
 *       false
 *   );
 *
 * No contiene contraseñas.
 * No crea usuarios.
 * No concede ownership al runtime.
 */

DO $$
DECLARE
    v_database TEXT := current_database();
    v_migrator TEXT := current_setting(
        'homex.migrator_role',
        true
    );
    v_runtime TEXT := current_setting(
        'homex.runtime_role',
        true
    );
BEGIN
    IF v_migrator IS NULL OR btrim(v_migrator) = '' THEN
        RAISE EXCEPTION
            'Debe definir homex.migrator_role antes de aplicar privilegios';
    END IF;

    IF v_runtime IS NULL OR btrim(v_runtime) = '' THEN
        RAISE EXCEPTION
            'Debe definir homex.runtime_role antes de aplicar privilegios';
    END IF;

    IF current_user <> v_migrator THEN
        RAISE EXCEPTION
            'El script debe ejecutarse como %, usuario actual: %',
            v_migrator,
            current_user;
    END IF;

    /*
     * El acceso a la base queda explícitamente limitado.
     * Superusuarios PostgreSQL conservan sus capacidades administrativas.
     */
    EXECUTE format(
        'REVOKE ALL ON DATABASE %I FROM PUBLIC',
        v_database
    );

    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO %I, %I',
        v_database,
        v_migrator,
        v_runtime
    );

    /*
     * PUBLIC no debe permitir crear objetos arbitrarios.
     */
    REVOKE CREATE ON SCHEMA public FROM PUBLIC;

    /*
     * El migrador mantiene capacidad DDL.
     */
    EXECUTE format(
        'GRANT USAGE, CREATE ON SCHEMA public TO %I',
        v_migrator
    );

    /*
     * El runtime sólo puede utilizar el schema.
     * Se revocan permisos previos para hacer la operación idempotente
     * y evitar conservar privilegios históricos accidentales.
     */
    EXECUTE format(
        'REVOKE ALL ON SCHEMA public FROM %I',
        v_runtime
    );

    EXECUTE format(
        'GRANT USAGE ON SCHEMA public TO %I',
        v_runtime
    );

    /*
     * Tablas existentes:
     * únicamente DML necesario para Django/HOMEX.
     *
     * No se concede:
     *   TRUNCATE
     *   REFERENCES
     *   TRIGGER
     *   ownership
     */
    EXECUTE format(
        'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I',
        v_runtime
    );

    EXECUTE format(
        'GRANT SELECT, INSERT, UPDATE, DELETE '
        'ON ALL TABLES IN SCHEMA public TO %I',
        v_runtime
    );

    /*
     * Secuencias comerciales/Django.
     */
    EXECUTE format(
        'REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I',
        v_runtime
    );

    EXECUTE format(
        'GRANT USAGE, SELECT '
        'ON ALL SEQUENCES IN SCHEMA public TO %I',
        v_runtime
    );

    /*
     * Objetos futuros creados por el migrador.
     */
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I '
        'IN SCHEMA public '
        'REVOKE ALL ON TABLES FROM %I',
        v_migrator,
        v_runtime
    );

    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I '
        'IN SCHEMA public '
        'GRANT SELECT, INSERT, UPDATE, DELETE '
        'ON TABLES TO %I',
        v_migrator,
        v_runtime
    );

    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I '
        'IN SCHEMA public '
        'REVOKE ALL ON SEQUENCES FROM %I',
        v_migrator,
        v_runtime
    );

    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I '
        'IN SCHEMA public '
        'GRANT USAGE, SELECT ON SEQUENCES TO %I',
        v_migrator,
        v_runtime
    );
END;
$$;
