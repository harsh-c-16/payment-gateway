#!/usr/bin/env bash
set -euo pipefail

# Compose file-backed secrets keep the host owner's 0600 mode on Linux. The
# official entrypoint drops to postgres before running init scripts, so stage
# private copies while still root. Host secrets remain unchanged and the copies
# live only on the container's tmpfs, including on retained-volume recreation.
if [ "$(id -u)" = 0 ] && [ "${1:-}" = postgres ]; then
    export GROUP3_POSTGRES_SECRETS_DIR=/run/group3-postgres-secrets
    install -d -o postgres -g postgres -m 0700 "$GROUP3_POSTGRES_SECRETS_DIR"
    for service in admin conversation catalog orders inventory payments analytics; do
        source_file="/run/secrets/${service}_password"
        [ -s "$source_file" ] || { echo "Missing PostgreSQL secret: $service" >&2; exit 1; }
        install -o postgres -g postgres -m 0600 \
            "$source_file" "$GROUP3_POSTGRES_SECRETS_DIR/${service}_password"
    done
    export POSTGRES_PASSWORD_FILE="$GROUP3_POSTGRES_SECRETS_DIR/admin_password"
fi

exec /usr/local/bin/docker-entrypoint.sh "$@"
