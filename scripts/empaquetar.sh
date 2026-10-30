#!/usr/bin/env bash
# Construye el ejecutable con PyInstaller.
#
#   scripts/empaquetar.sh
#
# El resultado queda en dist/taller-equipos/: esa carpeta se copia entera a la PC
# del taller y se ejecuta el binario de adentro. No hace falta Python instalado.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

echo "Regenerando el icono del ejecutable…"
uv run python scripts/generar_icono.py

echo "Empaquetando (esto tarda un minuto)…"
uv run pyinstaller packaging/taller-equipos.spec \
    --noconfirm --clean \
    --distpath dist --workpath build

BINARIO="$RAIZ/dist/taller-equipos/taller-equipos"
echo
if [[ -x "$BINARIO" ]]; then
    echo "Listo: $BINARIO"
    echo "Tamaño del paquete: $(du -sh dist/taller-equipos | cut -f1)"
    echo "Versión del binario: $("$BINARIO" --version)"
else
    echo "error: no se generó el binario" >&2
    exit 1
fi
