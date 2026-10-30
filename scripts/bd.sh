#!/usr/bin/env bash
# Gestión del clúster de PostgreSQL del taller.
#
# Es una instalación keg-only de Homebrew, no un servicio del sistema: no
# arranca sola al iniciar sesión. Este script es el único lugar donde viven los
# comandos, para no tener que recordarlos de memoria.
#
#   scripts/bd.sh start    levanta el clúster si no está corriendo
#   scripts/bd.sh stop     lo detiene limpiamente
#   scripts/bd.sh status   dice si está corriendo y con qué argumentos
#   scripts/bd.sh psql     abre psql como superusuario de desarrollo
#
# Rutas sobreescribibles con PGBIN, PGDATA_TALLER y PGPORT.
set -euo pipefail

PGBIN="${PGBIN:-/home/linuxbrew/.linuxbrew/opt/postgresql@18/bin}"
DATA="${PGDATA_TALLER:-/home/linuxbrew/.linuxbrew/var/postgresql@18}"
PORT="${PGPORT:-5432}"
BASE="${TALLER_BASE:-taller_dev}"
DUENIO="${TALLER_DUENIO:-$(id -un)}"

existe_cluster() {
    [[ -f "$DATA/PG_VERSION" ]]
}

corriendo() {
    "$PGBIN/pg_ctl" -D "$DATA" status >/dev/null 2>&1
}

case "${1:-status}" in
    start)
        if ! existe_cluster; then
            echo "error: no hay clúster en $DATA" >&2
            echo "creálo con: $PGBIN/initdb -D \"$DATA\" -E UTF8 --locale=C -U $DUENIO" >&2
            exit 1
        fi
        if corriendo; then
            echo "PostgreSQL ya está corriendo en el puerto $PORT."
            exit 0
        fi
        echo "Levantando PostgreSQL desde $DATA…"
        "$PGBIN/pg_ctl" -D "$DATA" -l "$DATA/server.log" \
            -o "-c listen_addresses=localhost -p $PORT" -w start
        ;;
    stop)
        if ! corriendo; then
            echo "PostgreSQL no está corriendo."
            exit 0
        fi
        "$PGBIN/pg_ctl" -D "$DATA" -m fast stop
        ;;
    status)
        if corriendo; then
            "$PGBIN/pg_ctl" -D "$DATA" status
            "$PGBIN/pg_isready" -h localhost -p "$PORT" || true
        else
            echo "PostgreSQL no está corriendo (datos en $DATA)."
            exit 3
        fi
        ;;
    psql)
        # Por socket, no por TCP: pg_hba exige contraseña scram en loopback para
        # todo rol salvo taller_ro, y el superusuario de desarrollo no tiene una.
        # El socket local es trust para el usuario del sistema operativo.
        shift
        exec "$PGBIN/psql" -h "${PGHOST_SOCKET:-/tmp}" -p "$PORT" -U "$DUENIO" -d "$BASE" "$@"
        ;;
    *)
        echo "uso: $0 {start|stop|status|psql [argumentos de psql]}" >&2
        exit 2
        ;;
esac
