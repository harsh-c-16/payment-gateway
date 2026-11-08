"""Provision SELECT-only audit roles using the existing local admin secret binding."""

import re
import secrets

import psycopg
from psycopg import sql

from infra import postgres

SERVICES = ("analytics", "catalog", "inventory")


def audit_password(service, *, create=False):
    if service not in SERVICES:
        raise ValueError("Unknown audit database")
    path = postgres.RUNTIME / "secrets" / f"{service}_audit_password"
    if not path.exists() and create:
        with path.open("x", encoding="ascii") as stream:
            stream.write(secrets.token_urlsafe(32))
        path.chmod(0o600)
    if not path.is_file():
        raise postgres.SetupError(
            "Audit credentials missing; run the infrastructure env up adapter"
        )
    value = path.read_text(encoding="ascii")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", value):
        raise postgres.SetupError("Invalid audit credential file; restore the original")
    return value


def database_url(service):
    return (
        f"postgresql://{service}_audit_user:{audit_password(service)}@127.0.0.1:5432/{service}_db"
    )


def provision():
    values = postgres.credentials()
    for service in SERVICES:
        role, database = service + "_audit_user", service + "_db"
        path = postgres.RUNTIME / "secrets" / f"{service}_audit_password"
        with psycopg.connect(
            host="127.0.0.1",
            dbname=database,
            user="group3_admin",
            password=values["admin"],
            autocommit=True,
            connect_timeout=5,
        ) as tx:
            tx.execute("SELECT pg_advisory_lock(744031009)")
            existing = tx.execute(
                "SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,rolinherit "
                "FROM pg_roles WHERE rolname=%s",
                (role,),
            ).fetchone()
            if existing and (not path.is_file() or any(existing)):
                raise postgres.SetupError(
                    "Existing audit role requires its original restricted credentials"
                )
            password = audit_password(service, create=True)
            if existing is None:
                tx.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE "
                        "NOREPLICATION NOBYPASSRLS NOINHERIT CONNECTION LIMIT 4"
                    ).format(sql.Identifier(role), sql.Literal(password))
                )
            tx.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(database), sql.Identifier(role)
                )
            )
            tx.execute(
                sql.SQL("ALTER ROLE {} IN DATABASE {} SET default_transaction_read_only=on").format(
                    sql.Identifier(role), sql.Identifier(database)
                )
            )
            tx.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
            tx.execute(
                sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(
                    sql.Identifier(role)
                )
            )
            tx.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
                    "GRANT SELECT ON TABLES TO {}"
                ).format(sql.Identifier(service + "_user"), sql.Identifier(role))
            )
    private = postgres.RUNTIME / "audit.env"
    private.write_text(
        "".join(
            f"{service.upper()}_AUDIT_DATABASE_URL={database_url(service)}\n"
            for service in SERVICES
        ),
        encoding="utf-8",
    )
    private.chmod(0o600)
