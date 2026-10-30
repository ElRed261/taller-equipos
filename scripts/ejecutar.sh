#!/usr/bin/env bash
# Levanta la aplicación del taller de equipos.
#
#   scripts/ejecutar.sh
#
# Hace tres cosas, en orden:
#   1. si el clúster de PostgreSQL no está corriendo, lo levanta;
#   2. espera a que la base acepte conexiones (no alcanza con que el proceso viva);
#   3. abre la ventana.
#
# El usuario de la aplicación sale de TALLER_USUARIO. Si no está definido, la
# aplicación lo pregunta al arrancar: cada edición queda auditada a ese nombre,
# y por eso no se toma del sistema operativo.
#
#   TALLER_USUARIO=ana scripts/ejecutar.sh
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

PGBIN="${PGBIN:-/home/linuxbrew/.linuxbrew/opt/postgresql@18/bin}"
DATA="${PGDATA_TALLER:-/home/linuxbrew/.linuxbrew/var/postgresql@18}"
PORT="${PGPORT:-5432}"

if ! "$PGBIN/pg_ctl" -D "$DATA" status >/dev/null 2>&1; then
    echo "PostgreSQL no está corriendo: lo levanto."
    "$RAIZ/scripts/bd.sh" start
fi

# pg_ctl -w espera al proceso; la base puede tardar un instante más en aceptar
# conexiones, así que se insiste con pg_isready en vez de asumir.
for _ in $(seq 1 30); do
    if "$PGBIN/pg_isready" -h localhost -p "$PORT" -q; then
        break
    fi
    sleep 0.5
done

if ! "$PGBIN/pg_isready" -h localhost -p "$PORT" >/dev/null; then
    echo "error: PostgreSQL no responde en localhost:$PORT" >&2
    echo "revisá el registro: $DATA/server.log" >&2
    exit 1
fi

echo "Base lista. Abriendo la aplicación…"
exec uv run python -m taller.main "$@"
