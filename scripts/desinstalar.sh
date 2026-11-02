#!/usr/bin/env bash
# Desinstala el taller de equipos y dice qué encontró antes de tocar nada.
#
#   scripts/desinstalar.sh                      muestra qué haría (no borra nada)
#   scripts/desinstalar.sh --si                 lo hace
#   scripts/desinstalar.sh --si --con-configuracion   y borra la configuración
#   scripts/desinstalar.sh --si --prefijo /opt/taller  otra ubicación
#
# Busca en los lugares donde puede haber quedado algo:
#
#   - una instalación hecha con packaging/linux/instalar.sh (~/.local, /usr/local)
#   - el paquete construido (dist/ y build/)
#   - la configuración del usuario (~/.config/Taller de equipos)
#
# NO toca la base de datos ni sus roles: los datos no son del programa. Al final
# imprime los comandos exactos por si también querés borrar eso.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/Taller de equipos"
HACER=0
CON_CONFIG=0
PREFIJOS=("$HOME/.local" "/usr/local")

while [[ $# -gt 0 ]]; do
  case "$1" in
    --si) HACER=1; shift ;;
    --con-configuracion) CON_CONFIG=1; shift ;;
    --prefijo) PREFIJOS=("${2:-}"); shift 2 ;;
    -h|--help) sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "opción desconocida: $1" >&2; exit 2 ;;
  esac
done

encontrado=0
borrar() {
  encontrado=1
  if [[ "$HACER" == "1" ]]; then
    rm -rf "$1"
    echo "  borrado:   $1"
  else
    echo "  borraría:  $1"
  fi
}

echo "Buscando el programa…"
for prefijo in "${PREFIJOS[@]}"; do
  [[ -d "$prefijo/lib/taller-equipos" ]] && borrar "$prefijo/lib/taller-equipos"
  [[ -e "$prefijo/bin/taller-equipos" ]] && borrar "$prefijo/bin/taller-equipos"
  [[ -e "$prefijo/share/applications/taller-equipos.desktop" ]] && \
    borrar "$prefijo/share/applications/taller-equipos.desktop"
  [[ -e "$prefijo/share/icons/hicolor/256x256/apps/taller-equipos.png" ]] && \
    borrar "$prefijo/share/icons/hicolor/256x256/apps/taller-equipos.png"
  [[ -d "$prefijo/share/taller-equipos" ]] && borrar "$prefijo/share/taller-equipos"
done

# Una instalación abandonada deja lanzadores que apuntan a la nada.
if command -v taller-equipos > /dev/null 2>&1; then
  echo "  ojo: todavía hay un «taller-equipos» en el PATH: $(command -v taller-equipos)"
fi

echo "Buscando el paquete construido…"
[[ -d "$RAIZ/dist" ]] && borrar "$RAIZ/dist"
[[ -d "$RAIZ/build" ]] && borrar "$RAIZ/build"

if [[ "$CONFIG" != "" && -d "$CONFIG" ]]; then
  if [[ "$CON_CONFIG" == "1" ]]; then
    echo "Configuración (nombre, logo, conexión, ajuste del ingreso):"
    borrar "$CONFIG"
  else
    encontrado=1
    echo "  queda:     $CONFIG"
    echo "             (nombre, logo, conexión y el ajuste del ingreso)"
    echo "             para borrarla también: --con-configuracion"
  fi
fi

echo
if [[ "$encontrado" == "0" ]]; then
  echo "No hay nada instalado en los lugares conocidos."
  echo "Si el programa te abre desde algún lado, decime la ruta y la agrego:"
  echo "  scripts/desinstalar.sh --prefijo <esa carpeta>/.."
else
  if [[ "$HACER" == "0" ]]; then
    echo "Esto no borró nada. Para hacerlo:"
    echo "  scripts/desinstalar.sh --si"
    echo "  scripts/desinstalar.sh --si --con-configuracion   # y también la configuración"
  else
    echo "Listo."
  fi
fi

cat <<'BASE'

La base de datos y sus roles NO se tocaron. Si de verdad querés borrarlos (se van
los 568 registros y todo el historial), un administrador tiene que ejecutar:

    DROP DATABASE taller_dev;
    DROP ROLE taller_app;
    DROP ROLE taller_ro;

Y si arrancaste PostgreSQL como servicio:  brew services stop postgresql@18
BASE
