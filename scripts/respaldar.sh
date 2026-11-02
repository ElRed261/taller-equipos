#!/usr/bin/env bash
# Respaldo de la base del taller, con verificación y retención.
#
#   scripts/respaldar.sh              respalda y deja constancia en el registro
#   scripts/respaldar.sh --verificar  además restaura en una base descartable
#                                     y compara los conteos con producción
#
# Nunca deja un archivo a medias con nombre de bueno: escribe en un temporal y
# recién al final lo renombra. Si el volcado falla, el temporal se borra y el
# script sale con código distinto de cero, que es lo que mira el cron.
#
# Variables: TALLER_RESPALDOS (destino), TALLER_RETENCION_DIAS (30),
# TALLER_DATABASE_URL, PGBIN, PGPORT.
set -euo pipefail

PGBIN="${PGBIN:-/home/linuxbrew/.linuxbrew/opt/postgresql@18/bin}"
export PATH="$PGBIN:$PATH"
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESTINO="${TALLER_RESPALDOS:-$HOME/respaldos-taller}"
RETENCION="${TALLER_RETENCION_DIAS:-30}"
REGISTRO="$DESTINO/registro.log"
MOMENTO="$(date +%Y%m%d-%H%M%S)"

rojo() { printf '\033[31m%s\033[0m\n' "$*"; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }

anotar() {
  # Registro con fecha y hora: lo que después permite saber si hubo un hueco.
  mkdir -p "$DESTINO"
  printf '%s\t%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$REGISTRO"
}

resolver_url() {
  if [[ -n "${TALLER_DATABASE_URL:-}" ]]; then
    printf '%s' "$TALLER_DATABASE_URL"
    return
  fi
  local archivo="$RAIZ/.env"
  if [[ -f "$archivo" ]]; then
    # Solo la línea de la URL, sin exportar nada más del .env.
    sed -n 's/^TALLER_DATABASE_URL=//p' "$archivo" | head -1
  fi
}

URL="$(resolver_url)"
if [[ -z "$URL" ]]; then
  rojo "No hay conexión configurada. Poné TALLER_DATABASE_URL o un .env con esa línea."
  exit 1
fi

# La URL de SQLAlchemy lleva el dialecto adelante; pg_dump quiere la de siempre.
URL_PG="${URL/postgresql+psycopg:\/\//postgresql://}"
URL_PG="${URL_PG/postgresql+psycopg2:\/\//postgresql://}"
URL_PG="${URL_PG/sqlite+aiosqlite:*/-}"   # por si alguien apunta a otra cosa

mkdir -p "$DESTINO"
ARCHIVO="$DESTINO/taller-$MOMENTO.dump"
# Dos corridas en el mismo segundo no se pisan: la segunda lleva sufijo.
sufijo=1
while [[ -e "$ARCHIVO" ]]; do
  sufijo=$((sufijo + 1))
  ARCHIVO="$DESTINO/taller-$MOMENTO-$sufijo.dump"
done
TEMPORAL="$ARCHIVO.parcial"

limpiar() { rm -f "$TEMPORAL"; }
trap limpiar EXIT

echo "Respaldando en $ARCHIVO…"

# --no-owner: el respaldo se restaura con otro rol sin pelearse por los dueños.
if ! pg_dump --format=custom --no-owner --no-privileges --file="$TEMPORAL" "$URL_PG"; then
  rojo "Falló pg_dump. No se guardó nada."
  anotar "FALLA volcado"
  exit 1
fi

# Un archivo que pg_restore no puede leer no es un respaldo.
if ! pg_restore --list "$TEMPORAL" > /dev/null; then
  rojo "El archivo no se puede leer con pg_restore. No se guarda."
  anotar "FALLA ilegible"
  exit 1
fi

mv "$TEMPORAL" "$ARCHIVO"
trap - EXIT
TAMANO="$(du -h "$ARCHIVO" | cut -f1)"

# Conteos del momento: son contra qué se compara una restauración.
SQL="select 'movimiento='||count(*) from movimiento;"
SQL="$SQL select 'area='||count(*) from area;"
SQL="$SQL select 'tecnico='||count(*) from tecnico;"
RESUMEN="$(psql -X -q -A -t -d "$URL_PG" -c "$SQL" | paste -sd' ' -)"

printf 'movimientos y catálogos: %s\n' "$RESUMEN" > "${ARCHIVO%.dump}.txt"
verde "Listo: $ARCHIVO ($TAMANO)"
anotar "OK $ARCHIVO $TAMANO $RESUMEN"

# Retención: se borran los volcados viejos, no el registro.
BORRADOS="$(find "$DESTINO" -maxdepth 1 -name 'taller-*.dump' -mtime "+$RETENCION" -print -delete | wc -l | tr -d ' ')"
if [[ "$BORRADOS" != "0" ]]; then
  echo "Se borraron $BORRADOS respaldo(s) de más de $RETENCION días."
  anotar "RETENCION borrados=$BORRADOS"
fi

# ---------------------------------------------------------------------------
# Verificación real: restaurar en una base descartable y comparar.
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "--verificar" ]]; then
  # La prueba se hace como administrador de la base (socket local, peer), que es
  # quien puede crear y borrar la base descartable.
  PRUEBA="respaldo_prueba_$(date +%s)"
  soltar() {
    psql -X -q -d postgres -c "drop database if exists \"$PRUEBA\"" > /dev/null 2>&1 || true
  }
  trap soltar EXIT

  echo
  echo "Restaurando en la base descartable $PRUEBA…"
  psql -X -q -d postgres -c "create database \"$PRUEBA\"" > /dev/null
  if ! pg_restore --no-owner --no-privileges -d "$PRUEBA" "$ARCHIVO" 2> /tmp/restauracion.log; then
    # pg_restore avisa por cosas menores; lo que decide son los conteos.
    echo "(pg_restore dejó advertencias; se comparan los conteos igual)"
  fi

  ESPERADO="$(psql -X -q -A -t -d "$URL_PG" -c 'select count(*) from movimiento' | tr -d ' ')"
  OBTENIDO="$(psql -X -q -A -t -d "$PRUEBA" -c 'select count(*) from movimiento' | tr -d ' ')"
  OTRA_TABLA="$(psql -X -q -A -t -d "$PRUEBA" -c 'select count(*) from auditoria_edicion' | tr -d ' ')"
  AQUI_TABLA="$(psql -X -q -A -t -d "$URL_PG" -c 'select count(*) from auditoria_edicion' | tr -d ' ')"
  soltar
  trap - EXIT

  if [[ "$ESPERADO" == "$OBTENIDO" && "$AQUI_TABLA" == "$OTRA_TABLA" ]]; then
    verde "La restauración coincide: $OBTENIDO movimientos, $OTRA_TABLA registros de auditoría."
    anotar "VERIFICACION OK movimiento=$OBTENIDO auditoria=$OTRA_TABLA"
  else
    rojo "La restauración NO coincide: producción $ESPERADO/$AQUI_TABLA, restaurado $OBTENIDO/$OTRA_TABLA."
    anotar "VERIFICACION FALLA esperado=$ESPERADO/$AQUI_TABLA obtenido=$OBTENIDO/$OTRA_TABLA"
    exit 1
  fi
fi
