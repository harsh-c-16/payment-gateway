#!/usr/bin/env bash
set -euo pipefail

psql --username "$POSTGRES_USER" --dbname postgres --set ON_ERROR_STOP=1 <<'SQL'
REVOKE ALL ON DATABASE postgres FROM PUBLIC;
REVOKE ALL ON DATABASE template1 FROM PUBLIC;
SQL

for service in conversation catalog orders inventory payments analytics; do
    connection_limit=10
    if [ "$service" = analytics ]; then connection_limit=14; fi
    # Keep this read separate from psql: a failed command substitution in an
    # argument otherwise lets initialization continue with an empty password.
    password_file="${GROUP3_POSTGRES_SECRETS_DIR:?Secret staging entrypoint required}/${service}_password"
    service_password="$(cat "$password_file")"
    [ -n "$service_password" ] || { echo "Empty PostgreSQL secret: $service" >&2; exit 1; }
    psql --username "$POSTGRES_USER" --dbname postgres --set ON_ERROR_STOP=1 \
        --set role="${service}_user" --set db="${service}_db" \
        --set password="$service_password" \
        --set connection_limit="$connection_limit" <<'SQL'
CREATE ROLE :"role" LOGIN PASSWORD :'password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
    CONNECTION LIMIT :connection_limit;
CREATE DATABASE :"db" OWNER :"role";
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
SQL
    psql --username "$POSTGRES_USER" --dbname "${service}_db" \
        --set ON_ERROR_STOP=1 <<'SQL'
REVOKE ALL ON SCHEMA public FROM PUBLIC;
SQL
done

psql --username "$POSTGRES_USER" --dbname catalog_db --set ON_ERROR_STOP=1 <<'SQL'
CREATE EXTENSION vector VERSION '0.8.1';
SQL
