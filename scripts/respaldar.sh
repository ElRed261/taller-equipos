#!/usr/bin/env bash
# Respaldo de la base del taller: volcado, verificación, cifrado y retención.
#
#   scripts/respaldar.sh              respalda y deja constancia en el registro
#   scripts/respaldar.sh --verificar  además restaura en una base descartable
#                                     y compara los conteos con producción
#
# Nunca deja un archivo a medias con nombre de bueno: escribe en un temporal,
# verifica que pg_restore lo pueda leer, lo cifra si hay clave, y recién al final
# lo renombra. Si algo falla, el temporal se borra y el script sale con código
# distinto de cero, que es lo que mira el cron.
#
# Cifrado (elegí uno):
#   TALLER_RESPALDO_GPG_RECIPIENTE  huella o correo de una clave pública. Es la
#                                   forma correcta: el servidor solo tiene la
#                                   pública y no puede descifrar sus propios
#                                   respaldos. La privada vive fuera.
#   TALLER_RESPALDO_CLAVE           archivo con la contraseña simétrica. Más fácil,
#                                   pero quien lea ese archivo abre los respaldos.
#
# Variables: TALLER_RESPALDOS, TALLER_RETENCION_DIAS, TALLER_DATABASE_URL,
# PGBIN, PGPORT.
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

resolver_url() {
  if [[ -n "${TALLER_DATABASE_URL:-}" ]]; then
    printf '%s' "$TALLER_DATABASE_URL"
    return
  fi
  local archivo="$RAIZ/.env"
  if [[ -f "$archivo" ]]; then
    sed -n 's/^TALLER_DATABASE_URL=//p' "$archivo" | head -1
  fi
}

URL="$(resolver_url)"
if [[ -z "$URL" ]]; then
  rojo "No hay conexión configurada. Poné TALLER_DATABASE_URL o un .env con esa línea."
  exit 1
fi

# pg_dump quiere la URL de libpq, no la del dialecto de SQLAlchemy.
URL_PG="${URL/postgresql+psycopg:\/\//postgresql://}"
URL_PG="${URL_PG/postgresql+psycopg2:\/\//postgresql://}"

# ---------------------------------------------------------------------------
# Modo de cifrado
# ---------------------------------------------------------------------------
EXTENSION=".dump"
CIFRADO="no"
declare -a GPG_CIFRAR=()
declare -a GPG_DESCIFRAR=()

if [[ -n "$RECIPIENTE" ]]; then
  CIFRADO="recipiente:$RECIPIENTE"
  EXTENSION=".dump.gpg"
  GPG_CIFRAR=(gpg --batch --yes --quiet --trust-model always
              --recipient "$RECIPIENTE" --output -)
  # Con la pública no se puede verificar el contenido ya cifrado.
elif [[ -n "$CLAVE" ]]; then
  if [[ ! -f "$CLAVE" ]]; then
    rojo "No existe el archivo de clave: $CLAVE"
    exit 1
  fi
  permisos="$(stat -c '%a' "$CLAVE" 2>/dev/null || echo '')"
  if [[ -n "$permisos" && "$permisos" != "600" && "$permisos" != "400" ]]; then
    rojo "El archivo de clave tiene permisos $permisos: cualquiera de la máquina abre los respaldos."
    rojo "Arreglalo con: chmod 600 $CLAVE"
    exit 1
  fi
  CIFRADO="simetrico"
  EXTENSION=".dump.gpg"
  GPG_CIFRAR=(gpg --batch --yes --quiet --symmetric --passphrase-file "$CLAVE" --output -)
  GPG_DESCIFRAR=(gpg --batch --yes --quiet --decrypt --passphrase-file "$CLAVE")
else
  amarillo "Aviso: el respaldo NO se cifra. Contiene nombres de personas."
  amarillo "Configurá TALLER_RESPALDO_GPG_RECIPIENTE o TALLER_RESPALDO_CLAVE."
fi

mkdir -p "$DESTINO"
ARCHIVO="$DESTINO/taller-$MOMENTO$EXTENSION"
sufijo=1
while [[ -e "$ARCHIVO" ]]; do
  sufijo=$((sufijo + 1))
  ARCHIVO="$DESTINO/taller-$MOMENTO-$sufijo$EXTENSION"
done
TEMPORAL="$DESTINO/.taller-$MOMENTO.dump.parcial"

limpiar() { rm -f "$TEMPORAL"; }
trap limpiar EXIT

echo "Respaldando en $ARCHIVO…"

# --no-owner --no-privileges: se restaura con otro rol sin pelear por los dueños.
if ! pg_dump --format=custom --no-owner --no-privileges --file="$TEMPORAL" "$URL_PG"; then
  rojo "Falló pg_dump. No se guardó nada."
  anotar "FALLA volcado"
  exit 1
fi

# Un archivo que pg_restore no puede leer no es un respaldo. Se verifica sobre el
# texto plano, que es el único momento en que se puede sin la clave privada.
if ! pg_restore --list "$TEMPORAL" > /dev/null; then
  rojo "El archivo no se puede leer con pg_restore. No se guarda."
  anotar "FALLA ilegible"
  exit 1
fi

if [[ "$EXTENSION" == ".dump.gpg" ]]; then
  if ! "${GPG_CIFRAR[@]}" < "$TEMPORAL" > "$ARCHIVO.parcial"; then
    rojo "Falló el cifrado. No se guarda nada."
    anotar "FALLA cifrado"
    rm -f "$ARCHIVO.parcial"
    exit 1
  fi
  mv "$ARCHIVO.parcial" "$ARCHIVO"
  rm -f "$TEMPORAL"

  # Con clave simétrica sí se puede comprobar que el cifrado se descifra y sigue
  # siendo un respaldo válido: es la única forma de saber que no quedó ilegible.
  # Se descifra a un temporal porque pg_restore necesita buscar dentro del archivo
  # y con una tubería no puede.
  if [[ ${#GPG_DESCIFRAR[@]} -gt 0 ]]; then
    comprobacion="$(mktemp)"
    if ! "${GPG_DESCIFRAR[@]}" < "$ARCHIVO" > "$comprobacion" \
       || ! pg_restore --list "$comprobacion" > /dev/null; then
      rojo "El respaldo cifrado no se puede descifrar o no es un volcado válido."
      anotar "FALLA descifrado"
      rm -f "$comprobacion" "$ARCHIVO"
      exit 1
    fi
    rm -f "$comprobacion"
  fi
else
  mv "$TEMPORAL" "$ARCHIVO"
fi
trap - EXIT

TAMANO="$(du -h "$ARCHIVO" | cut -f1)"

# Conteos del momento: son contra qué se compara una restauración.
SQL="select 'movimiento='||count(*) from movimiento;"
SQL="$SQL select 'area='||count(*) from area;"
SQL="$SQL select 'tecnico='||count(*) from tecnico;"
RESUMEN="$(psql -X -q -A -t -d "$URL_PG" -c "$SQL" | paste -sd' ' -)"

printf 'movimientos y catálogos: %s\n' "$RESUMEN" > "${ARCHIVO%.dump*}.txt"
printf 'cifrado: %s\n' "$CIFRADO" >> "${ARCHIVO%.dump*}.txt"
verde "Listo: $ARCHIVO ($TAMANO, cifrado: $CIFRADO)"
anotar "OK $ARCHIVO $TAMANO cifrado=$CIFRADO $RESUMEN"

# Retención: se borran los volcados viejos, no el registro.
BORRADOS="$(find "$DESTINO" -maxdepth 1 \( -name 'taller-*.dump' -o -name 'taller-*.dump.gpg' \) -mtime "+$RETENCION" -print -delete | wc -l | tr -d ' ')"
if [[ "$BORRADOS" != "0" ]]; then
  echo "Se borraron $BORRADOS respaldo(s) de más de $RETENCION días."
  anotar "RETENCION borrados=$BORRADOS"
fi

# ---------------------------------------------------------------------------
# Verificación real: restaurar en una base descartable y comparar.
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "--verificar" ]]; then
  # Se hace como administrador de la base (socket local, peer), que es quien
  # puede crear y borrar la base descartable.
  PRUEBA="respaldo_prueba_$(date +%s)"
  A_RESTAURAR="$ARCHIVO"
  DESCIFRADO=""

  soltar() {
    psql -X -q -d postgres -c "drop database if exists \"$PRUEBA\"" > /dev/null 2>&1 || true
    [[ -n "$DESCIFRADO" ]] && rm -f "$DESCIFRADO"
  }
  trap soltar EXIT

  if [[ "$EXTENSION" == ".dump.gpg" ]]; then
    if [[ ${#GPG_DESCIFRAR[@]} -eq 0 ]]; then
      rojo "No se puede verificar: el respaldo se cifró con una clave pública y acá no está la privada."
      anotar "VERIFICACION imposible sin clave privada"
      exit 1
    fi
    DESCIFRADO="$(mktemp)"
    "${GPG_DESCIFRAR[@]}" < "$ARCHIVO" > "$DESCIFRADO"
    A_RESTAURAR="$DESCIFRADO"
  fi

  echo
  echo "Restaurando en la base descartable $PRUEBA…"
  psql -X -q -d postgres -c "create database \"$PRUEBA\"" > /dev/null
  if ! pg_restore --no-owner --no-privileges -d "$PRUEBA" "$A_RESTAURAR" 2> /tmp/restauracion.log; then
    echo "(pg_restore dejó advertencias; lo que decide son los conteos)"
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
