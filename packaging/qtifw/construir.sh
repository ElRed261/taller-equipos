#!/usr/bin/env bash
# Instalador nativo con Qt Installer Framework (mismo wizard en Linux/Windows/macOS).
#
#   packaging/qtifw/construir.sh [-h|--help]
#
# Requisitos:
#
#   1. Un venv de construcción con pip sembrado (los uv-managed no lo traen y
#      pyside6-deploy lo exige) con PySide6 y Nuitka:
#        uv venv --seed .venv-deploy
#        uv pip install --python .venv-deploy/bin/python -e . pyside6 nuitka
#
#   2. binarycreator en el PATH (o exportar TALLER_QTIFW=ruta/binario). Es parte
#      de QtIFW, que se instala desde los Developer and Designer Tools de Qt.
#
# Resultado:
#
#   dist/taller-equipos-instalador        instalador offline con wizard QtIFW
#   dist/repositorio/                     si hay repogen: repo online para el
#                                         MaintenanceTool (auto-update contra el
#                                         servidor del taller)
#
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$RAIZ"

VERSION="${VERSION:-$(sed -n 's/^version = "\([^\"]*\)".*/\1/p' pyproject.toml | head -1)}"
DIST="$RAIZ/dist"
# pyside6-deploy respeta exec_directory del spec: dist/<nombre>.dist
DEPLOY="$DIST/taller-equipos.dist"
# Orden de búsqueda: variable de entorno → copia dentro del repo (aqt) → PATH.
if [[ -n "${TALLER_QTIFW:-}" ]]; then
    QTIFW_BIN="$TALLER_QTIFW"
else
    QTIFW_BIN="$(find Tools -type f -name binarycreator 2>/dev/null | sort | tail -1)"
    QTIFW_BIN="${QTIFW_BIN:-binarycreator}"
fi

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0
fi

if ! command -v "$QTIFW_BIN" > /dev/null 2>&1; then
    echo "error: no encontré binarycreator. Instalá QtIFW (Developer and Designer" >&2
    echo "Tools de Qt) y su bin/ al PATH, o TALLER_QTIFW=/ruta/binarycreator" >&2
    exit 1
fi

if [[ ! -d "$DEPLOY" ]]; then
    echo "Compilando con pyside6-deploy (esto tarda: Nuitka compila a C)…"
    .venv-deploy/bin/pyside6-deploy \
        --mode standalone \
        --name taller-equipos \
        --extra-ignore-dirs tests --extra-ignore-dirs docs \
        --extra-ignore-dirs odd --extra-ignore-dirs packaging \
        --force \
        -c packaging/pyside6deploy.spec \
        src/taller/main.py
fi

# El compilado a veces sale como main.bin (usa el nombre del entry point);
# se uniforma a taller-equipos.bin para que el wizard y los atajos sean iguales.
if [[ -e "$DEPLOY/main.bin" ]]; then
    mv "$DEPLOY/main.bin" "$DEPLOY/taller-equipos.bin"
fi
[[ -e "$DEPLOY/taller-equipos.bin" || -e "$DEPLOY/taller-equipos.exe" ]] \
    || { echo "error: pyside6-deploy no dejó el ejecutable en $DEPLOY" >&2; exit 1; }

# El ejecutable compilado necesita sus datos al lado: migraciones y assets.
echo "Copiando datos junto al ejecutable…"
rm -rf "$DEPLOY/migrations"
cp -a migrations "$DEPLOY/migrations"
# Nuitka no crea _internal (eso era PyInstaller): los assets van en su lugar propio.
mkdir -p "$DEPLOY/taller/ui"
rm -rf "$DEPLOY/taller/ui/assets"
cp -a src/taller/ui/assets "$DEPLOY/taller/ui/assets"

# Paquete de producción para QtIFW: árbol de producción + metadatos del asistente.
PKG="$RAIZ/packaging/qtifw/packages/taller-equipos"
rm -rf "$PKG/data"
mkdir -p "$PKG/data"
cp -a "$DEPLOY/." "$PKG/data/"

# Versión y fecha del momento en los metadatos del componente.
python3 - "$VERSION" "$PKG/meta/package.xml" <<'PY'
import datetime as dt
import sys

version, ruta = sys.argv[1], sys.argv[2]
texto = open(ruta, encoding="utf-8").read()
texto = texto.replace("<Version>1.0.0</Version>", f"<Version>{version}</Version>")
texto = texto.replace(
    "<ReleaseDate>2026-11-02</ReleaseDate>",
    f"<ReleaseDate>{dt.date.today().isoformat()}</ReleaseDate>",
)
open(ruta, "w", encoding="utf-8").write(texto)
PY

echo "Construyendo el instalador offline…"
mkdir -p "$DIST"
rm -f "$DIST/taller-equipos-instalador"
"$QTIFW_BIN" -c packaging/qtifw/config/config.xml \
             -p packaging/qtifw/packages \
             "$DIST/taller-equipos-instalador"

# Repositorio online para el MaintenanceTool: lo pongo solo si repogen existe,
# porque para subirlo hace falta un servidor web, y esa decisión es del taller.
if command -v repogen > /dev/null 2>&1; then
    rm -rf "$DIST/repositorio"
    repogen --repository "$DIST/repositorio" packaging/qtifw/packages
    echo "Repo online: $DIST/repositorio (para el MaintenanceTool)."
fi

echo
echo "Listo: $DIST/taller-equipos-instalador"
echo "Recorrer el todo-lo-instala: $(du -sh "$PKG/data" | cut -f1)."
