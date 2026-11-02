#!/usr/bin/env bash
# Instalador de Linux del taller de equipos.
#
#   sudo packaging/linux/instalar.sh                  instala para todo el sistema
#   packaging/linux/instalar.sh                       instala solo para tu usuario
#   packaging/linux/instalar.sh --prefijo /opt/taller  elige dónde
#
# Copia el paquete que armó PyInstaller, deja un lanzador en el PATH, una entrada en
# el menú de aplicaciones y un desinstalador. Se puede volver a correr sobre una
# instalación existente: reemplaza la versión anterior y no toca la configuración
# del usuario, que vive en su carpeta personal.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ORIGEN="$RAIZ/dist/taller-equipos"
PREFIJO=""

rojo() { printf '\033[31m%s\033[0m\n' "$*"; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefijo) PREFIJO="${2:-}"; shift 2 ;;
    --origen) ORIGEN="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,12p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) rojo "opción desconocida: $1"; exit 2 ;;
  esac
done

# Sin --prefijo: sistema si hay permisos de root, usuario si no. Un instalador que
# siempre pide sudo se vuelve inútil en una PC donde la persona no administra.
if [[ -z "$PREFIJO" ]]; then
  if [[ $EUID -eq 0 ]]; then
    PREFIJO="/usr/local"
  else
    PREFIJO="$HOME/.local"
  fi
fi

if [[ ! -d "$ORIGEN" ]]; then
  rojo "No está el paquete: $ORIGEN"
  rojo "Armalo primero con: scripts/empaquetar.sh"
  exit 1
fi
if [[ ! -x "$ORIGEN/taller-equipos" ]]; then
  rojo "El paquete no tiene el ejecutable esperado: $ORIGEN/taller-equipos"
  exit 1
fi

DESTINO_APP="$PREFIJO/lib/taller-equipos"
BIN="$PREFIJO/bin/taller-equipos"
DESKTOP="$PREFIJO/share/applications/taller-equipos.desktop"
ICONO="$PREFIJO/share/icons/hicolor/256x256/apps/taller-equipos.png"

echo "Instalando en $PREFIJO…"
mkdir -p "$PREFIJO/lib" "$PREFIJO/bin" "$PREFIJO/share/applications" \
         "$PREFIJO/share/icons/hicolor/256x256/apps"

# Copia a una carpeta nueva y después cambia el nombre: si la copia falla a mitad de
# camino, la instalación anterior sigue entera y usable.
NUEVA="$DESTINO_APP.nueva"
rm -rf "$NUEVA"
mkdir -p "$NUEVA"
cp -a "$ORIGEN/." "$NUEVA/"
if grep -rqi "indomet" "$NUEVA" 2>/dev/null; then
  rojo "El paquete trae la marca institucional. Este instalador es para la versión"
  rojo "genérica: la marca se configura en la aplicación, no se empaqueta."
  rm -rf "$NUEVA"
  exit 1
fi
rm -rf "$DESTINO_APP"
mv "$NUEVA" "$DESTINO_APP"

cat > "$BIN" <<LANZADOR
#!/usr/bin/env bash
# Lanzador generado por el instalador del taller de equipos.
exec "$DESTINO_APP/taller-equipos" "\$@"
LANZADOR
chmod 755 "$BIN"

if [[ -f "$ORIGEN/../icono.png" ]]; then
  cp -f "$ORIGEN/../icono.png" "$ICONO"
elif [[ -f "$RAIZ/packaging/icono.png" ]]; then
  cp -f "$RAIZ/packaging/icono.png" "$ICONO"
fi

cat > "$DESKTOP" <<DESKTOP_ENTRY
[Desktop Entry]
Type=Application
Name=Taller de equipos
Comment=Registro de entrada y salida de equipos
Exec=$BIN
Icon=$ICONO
Terminal=false
Categories=Office;Database;
DESKTOP_ENTRY

mkdir -p "$PREFIJO/share/taller-equipos"
cat > "$PREFIJO/share/taller-equipos/desinstalar.sh" <<'DESINSTALADOR'
#!/usr/bin/env bash
# Quita el programa. Por defecto NO toca la configuración ni la base de datos.
#
#   desinstalar.sh                        quita el programa, deja la configuración
#   desinstalar.sh --con-configuracion    quita también la configuración guardada
#
# La base de datos no se toca nunca: los datos no son del programa.
set -eu
DESTINO_APP="__DESTINO_APP__"
PREFIJO="__PREFIJO__"
BORRAR_CONFIG=0
[[ "${1:-}" == "--con-configuracion" ]] && BORRAR_CONFIG=1

rm -rf "$DESTINO_APP"
rm -f "$PREFIJO/bin/taller-equipos" \
      "$PREFIJO/share/applications/taller-equipos.desktop" \
      "$PREFIJO/share/icons/hicolor/256x256/apps/taller-equipos.png"
rm -rf "$PREFIJO/share/taller-equipos"

if [[ "$BORRAR_CONFIG" == "1" ]]; then
  CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/Taller de equipos"
  rm -rf "$CONFIG"
  echo "Programa y configuración eliminados ($CONFIG)."
else
  echo "Programa eliminado. La configuración sigue en ${XDG_CONFIG_HOME:-$HOME/.config}/Taller de equipos"
  echo "Para borrarla también: desinstalar.sh --con-configuracion"
fi
echo "La base de datos no se tocó: los datos no son del programa."
DESINSTALADOR
# Las rutas se escriben después, para que el desinstalador no dependa de dónde se
# lo llame ni de variables de entorno (quizás ya no exista ninguna).
sed -i "s|__DESTINO_APP__|$DESTINO_APP|; s|__PREFIJO__|$PREFIJO|" \
    "$PREFIJO/share/taller-equipos/desinstalar.sh"
chmod 755 "$PREFIJO/share/taller-equipos/desinstalar.sh"

# El menú de aplicaciones relee sus entradas; si no está, no es un error.
if command -v update-desktop-database > /dev/null 2>&1; then
  update-desktop-database "$PREFIJO/share/applications" > /dev/null 2>&1 || true
fi

VERSION="$("$BIN" --version 2>/dev/null || echo '(no respondió a --version)')"
verde "Instalado."
echo "  programa:   $DESTINO_APP"
echo "  lanzador:   $BIN"
echo "  versión:    $VERSION"
echo "  desinstalar: $PREFIJO/share/taller-equipos/desinstalar.sh"
case ":$PATH:" in
  *":$PREFIJO/bin:"*) ;;
  *) echo; echo "Aviso: $PREFIJO/bin no está en el PATH. Abrí el programa desde el menú de"
     echo "aplicaciones o llamalo con la ruta completa." ;;
esac
