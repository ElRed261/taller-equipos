#!/usr/bin/env bash
# Respaldo base del clúster: el punto de partida que hace posible el PITR.
#
#   scripts/respaldar_base.sh            base + verificación + cifrado
#
# Un respaldo lógico (`respaldar.sh`) sirve para recuperar datos, pero no permite
# volver a un minuto exacto. Para eso hacen falta dos cosas juntas:
#
#   1. un respaldo base físico (esto), y
#   2. los WAL archivados desde ese momento (archive_mode, ver docs/recuperacion.md).
#
# Con los dos, se restaura la base y se le aplican los WAL hasta el instante
# anterior al incidente. Sin el base, los WAL no sirven para nada.
#
# Se usa formato directorio (-Fp) porque es el único que `pg_verifybackup` puede
# verificar: un archivo que no se verificó no sirve como punto de partida.
#
# Variables: TALLER_RESPALDOS, TALLER_RETENCION_DIAS, TALLER_RESPALDO_CLAVE,
# TALLER_RESPALDO_GPG_RECIPIENTE, PGBIN, PGDATA_TALLER, PGPORT.
set -euo pipefail

PGBIN="${PGBIN:-/home/linuxbrew/.linuxbrew/opt/postgresql@18/bin}"
export PATH="$PGBIN:$PATH"
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESTINO="${TALLER_RESPALDOS:-$HOME/respaldos-taller}"
RETENCION="${TALLER_RETENCION_DIAS:-30}"
RECIPIENTE="${TALLER_RESPALDO_GPG_RECIPIENTE:-}"
CLAVE="${TALLER_RESPALDO_CLAVE:-}"
REGISTRO="$DESTINO/registro.log"
MOMENTO="$(date +%Y%m%d-%H%M%S)"

rojo() { printf '\033[31m%s\033[0m\n' "$*"; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }
amarillo() { printf '\033[33m%s\033[0m\n' "$*"; }

anotar() {
  mkdir -p "$DESTINO"
  printf '%s\t%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$REGISTRO"
}

if ! psql -X -q -A -t -d postgres -c \
    "select 1 from pg_settings where name='archive_mode' and setting='on'" | grep -q 1; then
  rojo "archive_mode está apagado: un respaldo base sin WAL archivados no permite PITR."
  rojo "Ver docs/recuperacion.md, sección PITR."
  exit 1
fi

mkdir -p "$DESTINO"
SALIDA="$DESTINO/base-$MOMENTO"
sufijo=1
while [[ -e "$SALIDA".tar.gz.gpg || -e "$SALIDA".tar.gz || -e "$SALIDA" ]]; do
  sufijo=$((sufijo + 1))
  SALIDA="$DESTINO/base-$MOMENTO-$sufijo"
done
CRUDO="$DESTINO/.base-$MOMENTO.parcial"

limpiar() { rm -rf "$CRUDO"; }
trap limpiar EXIT

echo "Respaldo base en $CRUDO…"

# -Fp: directorio, para poder verificarlo. -X stream: los WAL que hacen falta van
# dentro del respaldo, así no depende de que el archivado ya haya corrido.
if ! pg_basebackup --format=plain --wal-method=stream --checkpoint=fast \
        --progress --no-password --pgdata="$CRUDO"; then
  rojo "Falló pg_basebackup. No se guardó nada."
  anotar "FALLA base"
  exit 1
fi

# pg_verifybackup compara cada archivo con el manifiesto que escribió el servidor.
if ! pg_verifybackup "$CRUDO" > /dev/null; then
  rojo "El respaldo base no pasa la verificación. No se guarda."
  anotar "FALLA verificacion base"
  exit 1
fi

# El respaldo incluye postgresql.conf, con la ruta del archivo y del socket: una
# copia sin esto no se puede levantar en otra máquina.
{
  echo "respaldo base del taller"
  echo "tomado: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "wal_archivado_hasta: $(psql -X -q -A -t -d postgres -c 'select last_archived_wal from pg_stat_archiver')"
  echo "wal_actual: $(psql -X -q -A -t -d postgres -c 'select pg_current_wal_lsn()')"
  echo "para restaurar: ver docs/recuperacion.md, sección PITR"
} > "$CRUDO/COMO-RESTAURAR.txt"

TAR="$SALIDA.tar.gz"
if ! tar -czf "$TAR.parcial" -C "$DESTINO" "$(basename "$CRUDO")"; then
  rojo "Falló el empaquetado."
  anotar "FALLA empaquetado base"
  exit 1
fi
mv "$TAR.parcial" "$TAR"
rm -rf "$CRUDO"
trap - EXIT

FINAL="$TAR"
if [[ -n "$RECIPIENTE" ]]; then
  gpg --batch --yes --quiet --trust-model always --recipient "$RECIPIENTE" \
      --output "$TAR.gpg" "$TAR" || { rojo "Falló el cifrado."; anotar "FALLA cifrado base"; exit 1; }
  rm -f "$TAR"
  FINAL="$TAR.gpg"
elif [[ -n "$CLAVE" ]]; then
  permisos="$(stat -c '%a' "$CLAVE" 2>/dev/null || echo '')"
  if [[ -n "$permisos" && "$permisos" != "600" && "$permisos" != "400" ]]; then
    rojo "El archivo de clave tiene permisos $permisos. chmod 600 $CLAVE"
    exit 1
  fi
  gpg --batch --yes --quiet --symmetric --passphrase-file "$CLAVE" \
      --output "$TAR.gpg" "$TAR" || { rojo "Falló el cifrado."; anotar "FALLA cifrado base"; exit 1; }
  rm -f "$TAR"
  FINAL="$TAR.gpg"
else
  amarillo "Aviso: el respaldo base NO se cifra y contiene toda la base."
fi

TAMANO="$(du -h "$FINAL" | cut -f1)"
verde "Listo: $FINAL ($TAMANO, verificado con pg_verifybackup)"
anotar "OK base $FINAL $TAMANO"

BORRADOS="$(find "$DESTINO" -maxdepth 1 -name 'base-*.tar.gz*' -mtime "+$RETENCION" -print -delete | wc -l | tr -d ' ')"
if [[ "$BORRADOS" != "0" ]]; then
  echo "Se borraron $BORRADOS respaldo(s) base de más de $RETENCION días."
  anotar "RETENCION base borrados=$BORRADOS"
fi
