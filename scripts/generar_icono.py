#!/usr/bin/env python3
"""Genera packaging/icono.png e icono.ico desde el logo de la aplicación.

Un icono de aplicación no es la imagen tal cual: va sobre un lienzo cuadrado, con
margen, y en varios tamaños para que se vea bien en la barra de tareas, en el
menú y en el ejecutable de Windows.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
ORIGEN = RAIZ / "src" / "taller" / "ui" / "assets" / "logo.png"
DESTINO = RAIZ / "packaging"
LADO = 512
MARGEN = 0.78


def main() -> int:
    if not ORIGEN.is_file():
        print(f"error: falta {ORIGEN}", file=sys.stderr)
        return 1
    DESTINO.mkdir(exist_ok=True)
    imagen = Image.open(ORIGEN).convert("RGBA")

    lienzo = Image.new("RGBA", (LADO, LADO), (255, 255, 255, 0))
    limite = int(LADO * MARGEN)
    proporcion = min(limite / imagen.width, limite / imagen.height)
    escalada = imagen.resize(
        (int(imagen.width * proporcion), int(imagen.height * proporcion)), Image.LANCZOS
    )
    lienzo.paste(
        escalada,
        ((LADO - escalada.width) // 2, (LADO - escalada.height) // 2),
        escalada,
    )

    lienzo.save(DESTINO / "icono.png")
    lienzo.save(
        DESTINO / "icono.ico",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"icono.png e icono.ico generados en {DESTINO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
