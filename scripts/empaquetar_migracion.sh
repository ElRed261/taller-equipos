#!/usr/bin/env bash
# Paquete de migración: todo lo necesario para levantar la base en otro servidor.
#
#   scripts/empaquetar_migracion.sh              crea el paquete y lo verifica
#   scripts/empaquetar_migracion.sh --sin-verificar
#
# Deja una carpeta con fecha, permisos cerrados y sumas de verificación:
#
#   taller_dev.dump   volcado completo (esquema + datos), formato custom
#   roles.sql         todos los roles del clúster, con sus contraseñas hasheadas
#   manifiesto.txt    versiones, codificación, extensiones y conteos del momento
#   LEEME-MIGRACION.md  qué hacer en el servidor, paso por paso
#   SUMAS.sha256      para comprobar que nada se corrompió en el viaje
#
# El volcado va con --no-owner: en el servidor los roles se llaman distinto y los
# objetos se asignan al rol de aplicación al restaurar.
#
# Variables: TALLER_RESPALDOS (dónde dejar el paquete), TALLER_DATABASE_URL.
set -euo pipefail

PGBIN="${PGBIN:-/home/linuxbrew/.linuxbrew/opt/postgresql@18/bin}"
export PATH="$PGBIN:$PATH"
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESTINO="${TALLER_RESPALDOS:-$HOME/respaldos-taller}"
MOMENTO="$(date +%Y%m%d-%H%M)"
PAQUETE="$DESTINO/migracion-$MOMENTO"

rojo() { printf '\033[31m%s\033[0m\n' "$*"; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }

resolver_url() {
  if [[ -n "${TALLER_DATABASE_URL:-}" ]]; then
    printf '%s' "$TALLER_DATABASE_URL"
    return
  fi
  if [[ -f "$RAIZ/.env" ]]; then
    sed -n 's/^TALLER_DATABASE_URL=//p' "$RAIZ/.env" | head -1
  fi
}

URL="$(resolver_url)"
if [[ -z "$URL" ]]; then
  rojo "No hay conexión configurada. Poné TALLER_DATABASE_URL o un .env con esa línea."
  exit 1
fi
URL_PG="${URL/postgresql+psycopg:\/\//postgresql://}"
URL_PG="${URL_PG/postgresql+psycopg2:\/\//postgresql://}"

BASE="$(psql -X -q -A -t -d "$URL_PG" -c 'select current_database()')"
mkdir -p "$PAQUETE"
chmod 700 "$DESTINO" "$PAQUETE"
echo "Paquete de migración en $PAQUETE…"

# ------------------------------------------------------------------ volcado
if ! pg_dump --format=custom --no-owner --no-privileges \
        --file="$PAQUETE/taller_dev.dump.parcial" "$URL_PG"; then
  rojo "Falló pg_dump."
  rm -f "$PAQUETE/taller_dev.dump.parcial"
  exit 1
fi
mv "$PAQUETE/taller_dev.dump.parcial" "$PAQUETE/taller_dev.dump"

if ! pg_restore --list "$PAQUETE/taller_dev.dump" > "$PAQUETE/indice-del-volcado.txt"; then
  rojo "El volcado no se puede leer con pg_restore."
  exit 1
fi

# -------------------------------------------------------------------- roles
# Incluye los superusuarios y las contraseñas hasheadas: es el estado real del
# clúster. El LEEME explica por qué no conviene aplicarlo tal cual en producción.
# Con contraseñas de rol, que es lo que permite replicar el entorno: por eso el
# archivo se trata como un secreto y queda en 0600.
pg_dumpall --roles-only --file="$PAQUETE/roles.sql"

# --------------------------------------------------------------- manifiesto
{
  echo "paquete de migración del taller de equipos"
  echo "generado: $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "base: $BASE"
  echo "tamaño: $(psql -X -q -A -t -d "$URL_PG" -c "select pg_size_pretty(pg_database_size(current_database()))")"
  echo "servidor: $(psql -X -q -A -t -d "$URL_PG" -c 'select version()')"
  echo "codificación: $(psql -X -q -A -t -d "$URL_PG" -c "select pg_encoding_to_char(encoding)||' / '||datcollate||' / '||datctype from pg_database where datname=current_database()")"
  echo "extensiones: $(psql -X -q -A -t -d "$URL_PG" -c "select coalesce(string_agg(extname||' '||extversion, ', '),'ninguna') from pg_extension where extname <> 'plpgsql'")"
  echo "commit del código: $(git -C "$RAIZ" rev-parse --short HEAD 2>/dev/null || echo 'sin git')"
  echo
  echo "conteos:"
  psql -X -q -A -t -d "$URL_PG" -c "
    select '  '||relname||' = '||n_live_tup
    from pg_stat_user_tables where schemaname='public' order by relname;"
} > "$PAQUETE/manifiesto.txt"

# ------------------------------------------------------------------- LEEME
cat > "$PAQUETE/LEEME-MIGRACION.md" <<LEEME
# Migrar la base al servidor

Paquete generado el $(date '+%d/%m/%Y %H:%M'). Contiene el estado completo de la
base \`$BASE\` en ese momento.

| Archivo | Qué es |
| --- | --- |
| \`taller_dev.dump\` | volcado completo, formato custom (esquema y datos) |
| \`indice-del-volcado.txt\` | el contenido del volcado, tal como lo ve \`pg_restore --list\` |
| \`roles.sql\` | todos los roles del clúster, **incluido el superusuario de desarrollo** |
| \`manifiesto.txt\` | versiones, codificación, extensiones y conteos de ese momento |
| \`SUMAS.sha256\` | para comprobar que nada se corrompió al copiar |

## 1. Preparar el servidor

Hace falta PostgreSQL de la **misma versión mayor o más nueva** (este paquete viene
de la 18). Las extensiones \`pg_trgm\` y \`unaccent\` tienen que estar disponibles: en
Debian/Ubuntu vienen en \`postgresql-contrib\`.

\`\`\`sql
-- Como administrador del servidor, NO como el superusuario de desarrollo.
CREATE ROLE taller_app LOGIN PASSWORD 'una-clave-larga-y-unica';
CREATE ROLE taller_ro  LOGIN PASSWORD 'otra-clave-larga';

CREATE DATABASE taller_dev
  OWNER taller_app
  ENCODING 'UTF8'
  TEMPLATE template0;

\\c taller_dev
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
\`\`\`

> **No apliques \`roles.sql\` tal cual en producción.** Trae todos los roles que había
> en la máquina de desarrollo, entre ellos el superusuario personal, con su hash de
> contraseña. Sirve para replicar el entorno o para consultar qué había; para
> producción, creá los dos roles de arriba a mano.

## 2. Copiar el paquete

\`\`\`bash
scp -r migracion-*/ usuario@servidor:/tmp/
\`\`\`

## 3. Comprobar que llegó entero

\`\`\`bash
cd /tmp/migracion-*
sha256sum -c SUMAS.sha256
\`\`\`

Si algo no coincide, no sigas: volvé a copiar.

## 4. Restaurar

\`\`\`bash
pg_restore --no-owner --no-privileges -d taller_dev -U taller_app taller_dev.dump
\`\`\`

Con \`--no-owner\` los objetos quedan a nombre de \`taller_app\`, que es el dueño de la
base en el servidor. \`pg_restore\` puede avisar por permisos o por dueños que no
existen: se mira el resultado, no los avisos.

## 5. Verificar antes de abrir el sistema

Los números tienen que coincidir con \`manifiesto.txt\`:

\`\`\`sql
\\c taller_dev
select count(*) from movimiento;
select count(*) from area;
select count(*) from tecnico;
select count(*) from auditoria_edicion;
select estado, count(*) from v_movimiento_estado group by estado order by 1;
\`\`\`

## 6. Apuntar la aplicación al servidor

En la máquina que usa el programa: Configuración → Sistema → **Cambiar
configuración…**, y poné el host del servidor, la base \`taller_dev\` y el usuario
\`taller_app\`. O en el \`.env\`:

\`\`\`text
TALLER_DATABASE_URL=postgresql+psycopg://taller_app:CLAVE@SERVIDOR:5432/taller_dev?sslmode=require
\`\`\`

## 7. Cerrar la puerta del servidor

Con la base restaurada y la aplicación apuntando ahí, falta lo que en desarrollo ya
está hecho y en el servidor no:

- \`pg_hba.conf\`: reglas por base y rol, \`scram-sha-256\`, sin \`trust\` remoto.
- \`listen_addresses\` en la interfaz de la red interna, nunca \`0.0.0.0\`.
- TLS: \`ssl = on\` y \`sslmode=require\` en la cadena de conexión.
- Respaldos: cron con \`scripts/respaldar.sh --verificar\` y \`scripts/respaldar_base.sh\`,
  más \`archive_mode = on\` para PITR.
- Auditoría de estas reglas: \`uv run python scripts/verificar_seguridad_bd.py\`.

Todo está detallado en \`docs/seguridad.md\` y \`docs/recuperacion.md\` del repositorio.

## Lo que este paquete no incluye

- La **configuración de marca** (\`branding.json\`, el logo y el nombre de la
  organización): es local de cada instalación y está fuera del repositorio.
- El **código**: se instala con el instalador, no con el volcado.
- Los **archivos de configuración del clúster** (\`postgresql.conf\`, \`pg_hba.conf\`):
  dependen de la máquina y hay que escribirlos allá.
LEEME

# ------------------------------------------------------------------- sumas
( cd "$PAQUETE" && sha256sum taller_dev.dump roles.sql manifiesto.txt LEEME-MIGRACION.md \
    > SUMAS.sha256 )
# Después de escribir todo, porque un archivo creado después del chmod queda abierto.
chmod 600 "$PAQUETE"/*

# -------------------------------------------------------------- verificación
if [[ "${1:-}" != "--sin-verificar" ]]; then
  PRUEBA="migracion_prueba_$(date +%s)"
  soltar() { psql -X -q -d postgres -c "drop database if exists \"$PRUEBA\"" >/dev/null 2>&1 || true; }
  trap soltar EXIT

  echo
  echo "Restaurando el paquete en una base descartable para comprobarlo…"
  psql -X -q -d postgres -c "create database \"$PRUEBA\"" > /dev/null
  pg_restore --no-owner --no-privileges -d "$PRUEBA" "$PAQUETE/taller_dev.dump" 2>/dev/null || true

  for tabla in movimiento area tecnico auditoria_edicion; do
    aqui="$(psql -X -q -A -t -d "$URL_PG" -c "select count(*) from $tabla")"
    alla="$(psql -X -q -A -t -d "$PRUEBA" -c "select count(*) from $tabla")"
    if [[ "$aqui" != "$alla" ]]; then
      rojo "$tabla NO coincide: origen $aqui, restaurado $alla"
      exit 1
    fi
    echo "  $tabla = $alla"
  done
  soltar
  trap - EXIT
  verde "El paquete restaura completo y los conteos coinciden."
fi

TAMANO="$(du -sh "$PAQUETE" | cut -f1)"
verde "Listo: $PAQUETE ($TAMANO)"
echo "  archivos: $(ls -1 "$PAQUETE" | tr '\n' ' ')"
echo
echo "Antes de moverlo, cifralo con una frase que solo vos tengas:"
echo "  tar -czf - $PAQUETE | gpg --symmetric --output $PAQUETE.tar.gz.gpg"
