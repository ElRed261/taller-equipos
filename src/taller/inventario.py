"""Normalisation of inventory codes.

The legacy export typed the same code in several ways, and the institution
confirmed (2026-10-30) that the codes which *look* like they start with the letter
``O`` really start with a zero: ``O2071`` is ``02071`` and ``OO738`` is ``00738``.

That turns a former guess into a rule, so it can live in code:

* Leading ``O`` characters in an otherwise numeric code become zeros.
* Junk around a numeric core is removed: ``#02322`` → ``02322``, ``01916|`` → ``01916``.
* Spaces inside a numeric code are removed: ``0 1710`` → ``01710``.
* **Leading zeros are never stripped.** ``0776`` stays ``0776``; that is why the
  code is stored as text and not as a number.
* Anything that is not a numeric code (``Acer y Opiplet 7010``, ``YLTH614904``) is
  returned untouched, because the formatter does not invent structure it cannot see.

The explicit "there is no code" markers become ``None``.
"""

from __future__ import annotations

import re
from typing import Final

from taller.texto import clave_alias, normalizar_espacios

#: Explicit "there is no inventory code" markers. None of these is a code.
MARCADORES_SIN_CODIGO: Final = frozenset(
    {"n/a", "na", "n.a.", "---", "--", "-", "no", "no tiene"}
)

_BASURA_AL_INICIO = re.compile(r"^[^0-9A-Za-z]+")
_BASURA_AL_FINAL = re.compile(r"[^0-9A-Za-z]+$")
_DIGITOS_O_LETRA_O = re.compile(r"[0-9O]+")
_O_INICIAL = re.compile(r"^O+")
_SOLO_DIGITOS = re.compile(r"[0-9]+")

#: Ancho canónico de la serie de códigos numéricos.
#:
#: El archivo legado lo demuestra: los códigos con O inicial son ``O`` + 4 dígitos
#: (``O2071`` → ``02071``) y los que tenían dos son ``00`` + 3 dígitos (``OO738``
#: → ``00738``). Los dos casos son valores de 5 caracteres, igual que los códigos
#: nativos de 5 dígitos del archivo (``22182``, ``17018``). Por eso un código
#: numérico más corto se completa con ceros a la izquierda.
ANCHO_CODIGO: Final = 5


def normalizar_codigo(valor: str | None) -> str | None:
    """Return the canonical form of an inventory code, or ``None`` if there is none."""
    limpio = normalizar_espacios(valor)
    if limpio is None:
        return None
    if clave_alias(limpio) in MARCADORES_SIN_CODIGO:
        return None

    nucleo = _BASURA_AL_FINAL.sub("", _BASURA_AL_INICIO.sub("", limpio))
    if not nucleo:
        return limpio

    compacto = nucleo.replace(" ", "")
    if not _DIGITOS_O_LETRA_O.fullmatch(compacto):
        return nucleo  # no es un código numérico: se respeta como vino

    corregido = _O_INICIAL.sub(lambda coincidencia: "0" * len(coincidencia.group()), compacto)
    if _SOLO_DIGITOS.fullmatch(corregido):
        # Se completa a la izquierda: 1716 -> 01716, 776 -> 00776. Los ceros que
        # ya tiene se conservan y los códigos más largos no se tocan.
        return corregido.zfill(ANCHO_CODIGO)
    return nucleo


def es_codigo_numerico(valor: str | None) -> bool:
    """True when the value is only digits, i.e. a code that can carry leading zeros."""
    return bool(valor) and bool(_SOLO_DIGITOS.fullmatch(valor or ""))
