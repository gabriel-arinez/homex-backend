from __future__ import annotations

import os
import secrets
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
PRIVILEGIOS_SQL = ROOT / "docs/sql/privilegios_runtime.sql"

DATABASE_NAME = "homex_priv_f076_ci"
MIGRATOR_ROLE = "homex_migrator_f076_ci"
RUNTIME_ROLE = "homex_runtime_f076_ci"


def database_url(
    base_url: str,
    *,
    database: str,
    user: str,
    password: str,
) -> str:
    parsed = urlsplit(base_url)

    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 5432

    netloc = f"{quote(user, safe='')}:{quote(password, safe='')}@{host}:{port}"

    return urlunsplit(
        (
            parsed.scheme,
            netloc,
            f"/{database}",
            "",
            "",
        )
    )


def django_env(url: str) -> dict[str, str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    env.setdefault(
        "DJANGO_SECRET_KEY",
        "f076-privileges-test-only-secret-with-more-than-32-characters",
    )
    env.setdefault("DJANGO_ALLOWED_HOSTS", "testserver")
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
    return env


def ejecutar_manage(url: str, *args: str) -> None:
    subprocess.run(
        [sys.executable, "manage.py", *args],
        cwd=ROOT,
        env=django_env(url),
        check=True,
    )


def limpiar(admin_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as conn:
        admin_role = conn.execute("SELECT current_user").fetchone()[0]

        migrator_exists = (
            conn.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s",
                (MIGRATOR_ROLE,),
            ).fetchone()
            is not None
        )

        database_owner = conn.execute(
            """
            SELECT pg_get_userbyid(datdba)
            FROM pg_database
            WHERE datname = %s
            """,
            (DATABASE_NAME,),
        ).fetchone()

        if database_owner is not None:
            owner = database_owner[0]

            if owner == MIGRATOR_ROLE and migrator_exists:
                conn.execute(
                    sql.SQL("GRANT {} TO {} WITH SET TRUE, INHERIT FALSE").format(
                        sql.Identifier(MIGRATOR_ROLE),
                        sql.Identifier(admin_role),
                    )
                )

                conn.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(MIGRATOR_ROLE)))

                try:
                    conn.execute(
                        sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                            sql.Identifier(DATABASE_NAME)
                        )
                    )
                finally:
                    conn.execute("RESET ROLE")

            elif owner == admin_role:
                conn.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                        sql.Identifier(DATABASE_NAME)
                    )
                )

            else:
                raise RuntimeError(
                    f"No se puede limpiar {DATABASE_NAME}: su propietario inesperado es {owner}."
                )

        conn.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(RUNTIME_ROLE)))

        conn.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(MIGRATOR_ROLE)))


def crear_entorno(
    admin_url: str,
    migrator_password: str,
    runtime_password: str,
) -> None:
    limpiar(admin_url)

    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(
            sql.SQL(
                """
                CREATE ROLE {}
                    LOGIN
                    PASSWORD {}
                    NOSUPERUSER
                    NOCREATEDB
                    NOCREATEROLE
                """
            ).format(
                sql.Identifier(MIGRATOR_ROLE),
                sql.Literal(migrator_password),
            )
        )

        conn.execute(
            sql.SQL(
                """
                CREATE ROLE {}
                    LOGIN
                    PASSWORD {}
                    NOSUPERUSER
                    NOCREATEDB
                    NOCREATEROLE
                """
            ).format(
                sql.Identifier(RUNTIME_ROLE),
                sql.Literal(runtime_password),
            )
        )

        admin_role = conn.execute("SELECT current_user").fetchone()[0]

        conn.execute(
            sql.SQL("GRANT {} TO {} WITH SET TRUE, INHERIT FALSE").format(
                sql.Identifier(MIGRATOR_ROLE),
                sql.Identifier(admin_role),
            )
        )

        conn.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(DATABASE_NAME),
                sql.Identifier(MIGRATOR_ROLE),
            )
        )


def aplicar_privilegios(migrator_url: str) -> None:
    contenido = PRIVILEGIOS_SQL.read_text(encoding="utf-8")

    with psycopg.connect(migrator_url, autocommit=True) as conn:
        conn.execute(
            "SELECT set_config('homex.migrator_role', %s, false)",
            (MIGRATOR_ROLE,),
        )
        conn.execute(
            "SELECT set_config('homex.runtime_role', %s, false)",
            (RUNTIME_ROLE,),
        )
        conn.execute(contenido)


def probar_dml(runtime_url: str) -> None:
    with psycopg.connect(runtime_url, autocommit=True) as conn:
        conn.execute(
            """
            INSERT INTO django_session (
                session_key,
                session_data,
                expire_date
            )
            VALUES (
                'f076-runtime-smoke',
                'runtime-ok',
                '2099-01-01 00:00:00+00'
            )
            """
        )

        fila = conn.execute(
            """
            SELECT session_data
            FROM django_session
            WHERE session_key = 'f076-runtime-smoke'
            """
        ).fetchone()

        assert fila == ("runtime-ok",)

        conn.execute(
            """
            UPDATE django_session
            SET session_data = 'runtime-update-ok'
            WHERE session_key = 'f076-runtime-smoke'
            """
        )

        fila = conn.execute(
            """
            SELECT session_data
            FROM django_session
            WHERE session_key = 'f076-runtime-smoke'
            """
        ).fetchone()

        assert fila == ("runtime-update-ok",)

        conn.execute(
            """
            DELETE FROM django_session
            WHERE session_key = 'f076-runtime-smoke'
            """
        )

    print("runtime DML: OK")


def probar_orm(runtime_url: str) -> None:
    codigo = """
from django.contrib.auth import get_user_model

User = get_user_model()

usuario = User.objects.create_user(
    username="f076-runtime-orm"
)

assert User.objects.filter(pk=usuario.pk).exists()

User.objects.filter(pk=usuario.pk).delete()

print("runtime ORM: OK")
"""

    ejecutar_manage(
        runtime_url,
        "shell",
        "-c",
        codigo,
    )


def exigir_permiso_denegado(
    runtime_url: str,
    statement: str,
    etiqueta: str,
) -> None:
    with psycopg.connect(runtime_url, autocommit=True) as conn:
        try:
            conn.execute(statement)
        except psycopg.Error as exc:
            if exc.sqlstate != "42501":
                raise

            print(f"{etiqueta}: BLOQUEADO CORRECTAMENTE")
            return

    raise AssertionError(f"{etiqueta}: el usuario runtime obtuvo un privilegio DDL prohibido")


def main() -> None:
    admin_url = os.environ.get("F076_ADMIN_DATABASE_URL")

    if not admin_url:
        raise RuntimeError(
            "Falta F076_ADMIN_DATABASE_URL con una conexión PostgreSQL "
            "capaz de crear roles y bases descartables."
        )

    if not PRIVILEGIOS_SQL.exists():
        raise RuntimeError(f"No existe {PRIVILEGIOS_SQL}")

    migrator_password = secrets.token_urlsafe(24)
    runtime_password = secrets.token_urlsafe(24)

    migrator_url = database_url(
        admin_url,
        database=DATABASE_NAME,
        user=MIGRATOR_ROLE,
        password=migrator_password,
    )

    runtime_url = database_url(
        admin_url,
        database=DATABASE_NAME,
        user=RUNTIME_ROLE,
        password=runtime_password,
    )

    try:
        print("===== CREAR ENTORNO DESCARTABLE =====")
        crear_entorno(
            admin_url,
            migrator_password,
            runtime_password,
        )

        print("===== MIGRAR COMO MIGRATOR =====")
        ejecutar_manage(
            migrator_url,
            "migrate",
            "--noinput",
        )

        print("===== SEGUNDO MIGRATE =====")
        ejecutar_manage(
            migrator_url,
            "migrate",
            "--noinput",
        )

        print("===== APLICAR PRIVILEGIOS =====")
        aplicar_privilegios(migrator_url)

        print("===== DML RUNTIME =====")
        probar_dml(runtime_url)

        print("===== ORM RUNTIME =====")
        probar_orm(runtime_url)

        print("===== DDL PROHIBIDO =====")

        exigir_permiso_denegado(
            runtime_url,
            "CREATE TABLE runtime_no_debe_crear (id integer)",
            "CREATE TABLE",
        )

        exigir_permiso_denegado(
            runtime_url,
            """
            ALTER TABLE django_session
            ADD COLUMN runtime_no_debe_alterar integer
            """,
            "ALTER TABLE",
        )

        exigir_permiso_denegado(
            runtime_url,
            """
            CREATE FUNCTION public.runtime_no_debe_crear()
            RETURNS integer
            LANGUAGE sql
            AS 'SELECT 1'
            """,
            "CREATE FUNCTION",
        )

        print()
        print("F07.6 privilegios PostgreSQL: OK")

    finally:
        print("===== LIMPIEZA =====")
        limpiar(admin_url)


if __name__ == "__main__":
    main()
